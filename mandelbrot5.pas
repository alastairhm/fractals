program Mandelbrot5;

{ Interactive, multithreaded truecolor Mandelbrot explorer.
  Builds on mandelbrot4.pas (half-block pixels, smooth colouring, auto
  contrast) and adds:

    - keyboard pan / zoom / iteration control, redrawn in place
    - the view follows the terminal size, including resizes
    - rendering split across all CPU cores
    - points in the main cardioid and the period-2 bulb are detected
      directly instead of iterating them up to max_iter

  Keys:
    arrows / h j k l   pan
    + / =   zoom in        - / _   zoom out
    ]       more iterations   [   fewer iterations
    r       reset view        q / Esc / Ctrl-C   quit

  On quit the command line for the final view is printed, so you can come
  back to it later (or pass the same numbers to mandelbrot4).

  When output is not a terminal (piped or redirected) a single frame is
  drawn, like mandelbrot4, then the program exits.

  Build:  fpc -O2 mandelbrot5.pas
  Run:    ./mandelbrot5 [width] [rows] [max_iter] [centre_x] [centre_y] [zoom]

    width     terminal columns; 0 = fit the terminal   (default 0)
    rows      terminal rows; 0 = fit the terminal      (default 0)
    max_iter  iteration limit                          (default 500)
    centre_x  real part of view centre                 (default -0.75)
    centre_y  imag part of view centre                 (default 0)
    zoom      magnification; 1 shows the whole set    (default 1)

  The number of threads defaults to the number of online CPUs; set
  MANDELBROT_THREADS to override it.

  Run with -h or --help for usage. Linux only (uses termios and sysconf). }

{$mode objfpc}{$H+}
{$codepage utf8}

uses
  cthreads, Classes, SysUtils, Math, BaseUnix, termio, ctypes;

const
  Esc = #27;
  HalfBlock = #$E2#$96#$80;         { U+2580 UPPER HALF BLOCK, UTF-8 bytes }
  Bailout2 = 256.0 * 256.0;
  BaseSpan = 3.5;                   { real-axis width shown at zoom 1 }
  DefaultIter = 500;
  DefaultCX = -0.75;
  DefaultCY = 0.0;
  PanStep = 0.1;                    { fraction of the view moved per key }
  ZoomStep = 1.5;
  IterStep = 1.5;
  MinIter = 16;
  MaxIterLimit = 10000000;
  SC_NPROCESSORS_ONLN = 84;         { glibc value on Linux }

type
  TRGB = record
    R, G, B: Byte;
  end;

  TJobProc = procedure(Index: Integer);

  { A pool thread: sleeps on its own Start event, runs jobs, then reports
    back through DoneEvent. Threads live for the whole run, because
    TThread.WaitFor on the main thread polls in 100 ms steps and would
    add that much latency to every frame. }
  TWorker = class(TThread)
  private
    FStart: PRTLEvent;
  protected
    procedure Execute; override;
  public
    constructor Create;
    destructor Destroy; override;
  end;

function sysconf(Name: cint): clong; cdecl; external 'c' name 'sysconf';

var
  { View state }
  ArgWidth, ArgRows: Integer;       { 0 = follow the terminal }
  Width, Rows, MaxIter: Integer;    { Rows = picture rows (no status line) }
  CentreX, CentreY, Zoom: Double;
  SpanX, SpanY, X0, Y0, PixelSize: Double;

  { Frame buffers, shared with the worker threads }
  Values: array of Double;          { log smooth count per pixel, -1 = inside }
  RowMin, RowMax: array of Double;  { per pixel-row range of Values }
  Lines: array of string;           { one rendered terminal row each }
  ValMin, ValRange: Double;

  { Thread pool state }
  ThreadCount: Integer;
  JobProc: TJobProc;
  JobCount: Integer;
  NextJob: LongInt;
  Pool: array of TWorker;
  Busy: LongInt;                    { pool threads still running jobs }
  DoneEvent: PRTLEvent;
  PoolStopping: Boolean = False;

  { Terminal state }
  SavedTermios: termios;
  QuitRequested: Boolean = False;

  FS: TFormatSettings;              { '.' decimal separator, any locale }
  I: Integer;

{ ---------- arguments ---------- }

function IntArg(Index, Default: Integer): Integer;
begin
  if ParamCount >= Index then
    Result := StrToIntDef(ParamStr(Index), Default)
  else
    Result := Default;
end;

function FloatArg(Index: Integer; Default: Double): Double;
begin
  if ParamCount >= Index then
    Result := StrToFloatDef(ParamStr(Index), Default, FS)
  else
    Result := Default;
end;

function FloatText(X: Double; Digits: Integer): string;
begin
  Result := FloatToStrF(X, ffGeneral, Digits, 0, FS);
end;

{ ---------- threads ---------- }

{ Run JobProc(J) for J in 0..JobCount-1, sharing the jobs between the
  workers and the calling thread. Jobs are handed out one at a time, so
  slow rows (near the set) don't leave other threads idle. }
procedure RunJobs;
var
  J: LongInt;
begin
  repeat
    J := InterLockedIncrement(NextJob) - 1;
    if J >= JobCount then
      Break;
    JobProc(J);
  until False;
end;

constructor TWorker.Create;
begin
  FStart := RTLEventCreate;
  inherited Create(False);
end;

destructor TWorker.Destroy;
begin
  inherited Destroy;
  RTLEventDestroy(FStart);
end;

procedure TWorker.Execute;
begin
  repeat
    RTLEventWaitFor(FStart);
    if PoolStopping then
      Break;
    RunJobs;
    if InterLockedDecrement(Busy) = 0 then
      RTLEventSetEvent(DoneEvent);
  until False;
end;

procedure StartPool;
var
  K: Integer;
begin
  DoneEvent := RTLEventCreate;
  SetLength(Pool, ThreadCount - 1);   { the main thread is the last worker }
  for K := 0 to High(Pool) do
    Pool[K] := TWorker.Create;
end;

{ Tell the pool threads to exit. They are not waited for: they finish
  within microseconds, and the process is about to end anyway. }
procedure StopPool;
var
  K: Integer;
begin
  PoolStopping := True;
  for K := 0 to High(Pool) do
    RTLEventSetEvent(Pool[K].FStart);
end;

{ Run Proc(J) for J in 0..Count-1 on every thread, and return when all of
  them are done }
procedure RunParallel(Proc: TJobProc; Count: Integer);
var
  K: Integer;
begin
  JobProc := Proc;
  JobCount := Count;
  NextJob := 0;

  if Length(Pool) = 0 then
  begin
    RunJobs;
    Exit;
  end;

  Busy := Length(Pool);
  for K := 0 to High(Pool) do
    RTLEventSetEvent(Pool[K].FStart);
  RunJobs;
  RTLEventWaitFor(DoneEvent);
end;

function DetectThreads: Integer;
begin
  Result := StrToIntDef(GetEnvironmentVariable('MANDELBROT_THREADS'), 0);
  if Result <= 0 then
    Result := sysconf(SC_NPROCESSORS_ONLN);
  Result := EnsureRange(Result, 1, 256);
end;

{ ---------- rendering ---------- }

function RGB(R, G, B: Byte): TRGB;
begin
  Result.R := R; Result.G := G; Result.B := B;
end;

function SameRGB(const A, B: TRGB): Boolean;
begin
  Result := (A.R = B.R) and (A.G = B.G) and (A.B = B.B);
end;

{ Cosine gradient: deep blue -> cyan -> white -> orange as T goes 0..1 }
function Gradient(T: Double): TRGB;

  function Chan(Phase: Double): Byte;
  begin
    Result := Round(255 * (0.5 + 0.5 * Cos(2 * Pi * (T + Phase))));
  end;

begin
  T := T * 0.65;
  Result := RGB(Chan(0.50), Chan(0.60), Chan(0.75));
end;

{ Log of the smooth escape count for pixel (Px, Py), or -1 if inside }
function PixelValue(Px, Py: Integer): Double;
var
  Cx, Cy, Zx, Zy, Zx2, Zy2, Xq, Q, Y2, Smooth: Double;
  Iter: Integer;
begin
  Cx := X0 + (Px + 0.5) * PixelSize;
  Cy := Y0 - (Py + 0.5) * PixelSize;
  Y2 := Cy * Cy;

  { Main cardioid and period-2 bulb: never escape, so skip iterating }
  Xq := Cx - 0.25;
  Q := Xq * Xq + Y2;
  if Q * (Q + Xq) <= 0.25 * Y2 then
    Exit(-1);
  if Sqr(Cx + 1) + Y2 <= 0.0625 then
    Exit(-1);

  Zx := 0; Zy := 0; Zx2 := 0; Zy2 := 0;
  Iter := 0;
  while (Zx2 + Zy2 <= Bailout2) and (Iter < MaxIter) do
  begin
    Zy  := 2 * Zx * Zy + Cy;
    Zx  := Zx2 - Zy2 + Cx;
    Zx2 := Zx * Zx;
    Zy2 := Zy * Zy;
    Inc(Iter);
  end;

  if Iter >= MaxIter then
    Exit(-1);

  Smooth := Iter + 1 - Ln(0.5 * Ln(Zx2 + Zy2)) / Ln(2);
  Result := Ln(Max(Smooth, 1.0));
end;

{ Job for pass 1: compute one row of pixels and its value range }
procedure ComputeRow(Py: Integer);
var
  Px: Integer;
  V, Lo, Hi: Double;
begin
  Lo := MaxDouble;
  Hi := -1;
  for Px := 0 to Width - 1 do
  begin
    V := PixelValue(Px, Py);
    Values[Py * Width + Px] := V;
    if V >= 0 then
    begin
      Lo := Min(Lo, V);
      Hi := Max(Hi, V);
    end;
  end;
  RowMin[Py] := Lo;
  RowMax[Py] := Hi;
end;

function PixelColour(Px, Py: Integer): TRGB;
var
  V: Double;
begin
  V := Values[Py * Width + Px];
  if V < 0 then
    Exit(RGB(0, 0, 0));
  Result := Gradient((V - ValMin) / ValRange);
end;

{ Job for pass 2: turn two pixel rows into one terminal row of half blocks,
  only emitting colour codes that actually changed }
procedure DrawRow(Row: Integer);
var
  Col: Integer;
  Top, Bottom, LastFg, LastBg: TRGB;
  S: string;
begin
  S := '';
  LastFg := RGB(0, 0, 0);
  LastBg := RGB(0, 0, 0);
  for Col := 0 to Width - 1 do
  begin
    Top    := PixelColour(Col, Row * 2);
    Bottom := PixelColour(Col, Row * 2 + 1);
    if (Col = 0) or not SameRGB(Top, LastFg) then
      S := S + Esc + '[38;2;' + IntToStr(Top.R) + ';' + IntToStr(Top.G) + ';'
             + IntToStr(Top.B) + 'm';
    if (Col = 0) or not SameRGB(Bottom, LastBg) then
      S := S + Esc + '[48;2;' + IntToStr(Bottom.R) + ';' + IntToStr(Bottom.G)
             + ';' + IntToStr(Bottom.B) + 'm';
    LastFg := Top;
    LastBg := Bottom;
    S := S + HalfBlock;
  end;
  Lines[Row] := S + Esc + '[0m';
end;

{ Render the current view into Lines[0..Rows-1] }
procedure RenderFrame;
var
  PixRows, K: Integer;
  ValMax: Double;
begin
  { Square pixels: the vertical span follows from the width and row count }
  SpanX := BaseSpan / Zoom;
  PixelSize := SpanX / Width;
  SpanY := PixelSize * Rows * 2;
  X0 := CentreX - SpanX / 2;
  Y0 := CentreY + SpanY / 2;

  PixRows := Rows * 2;
  SetLength(Values, Width * PixRows);
  SetLength(RowMin, PixRows);
  SetLength(RowMax, PixRows);
  SetLength(Lines, Rows);

  RunParallel(@ComputeRow, PixRows);

  ValMin := MaxDouble;
  ValMax := -1;
  for K := 0 to PixRows - 1 do
  begin
    ValMin := Min(ValMin, RowMin[K]);
    ValMax := Max(ValMax, RowMax[K]);
  end;
  ValRange := Max(ValMax - ValMin, 1e-9);

  RunParallel(@DrawRow, Rows);
end;

{ ---------- terminal ---------- }

function TerminalSize(out Cols, TermRows: Integer): Boolean;
var
  WS: TWinSize;
begin
  Result := (fpIOCtl(1, TIOCGWINSZ, @WS) = 0) and (WS.ws_col > 0)
            and (WS.ws_row > 0);
  if Result then
  begin
    Cols := WS.ws_col;
    TermRows := WS.ws_row;
  end;
end;

procedure WriteOut(const S: string);
begin
  Write(S);
  Flush(Output);
end;

procedure OnSignal(Sig: cint); cdecl;
begin
  QuitRequested := True;
end;

procedure EnterRawMode;
var
  Raw: termios;
begin
  TCGetAttr(0, SavedTermios);
  Raw := SavedTermios;
  CFMakeRaw(Raw);
  Raw.c_cc[VMIN] := 0;              { read returns after at most VTIME }
  Raw.c_cc[VTIME] := 1;             { tenths of a second }
  TCSetAttr(0, TCSANOW, Raw);
  { Alternate screen, hide cursor }
  WriteOut(Esc + '[?1049h' + Esc + '[?25l');
end;

procedure LeaveRawMode;
begin
  WriteOut(Esc + '[0m' + Esc + '[?25h' + Esc + '[?1049l');
  TCSetAttr(0, TCSANOW, SavedTermios);
end;

{ ---------- interactive loop ---------- }

function CentreDigits: Integer;
begin
  { Enough significant digits to place the centre within a pixel }
  Result := EnsureRange(Ceil(Log10(Max(Zoom, 1.0) * Width)) + 3, 6, 17);
end;

function StatusLine(Ms: QWord): string;
var
  Warn: string;
begin
  { Doubles run out of precision when a pixel is ~1e-15 of the coordinate }
  if PixelSize < 1e-14 * Max(Max(Abs(CentreX), Abs(CentreY)), 1e-300) then
    Warn := '  PRECISION LIMIT'
  else
    Warn := '';
  Result := Format(' %s %s  zoom %s  iter %d  %d ms  %d threads%s  |  ' +
                   'arrows/hjkl pan  + - zoom  ] more iter  [ less iter  r reset  q quit',
                   [FloatText(CentreX, CentreDigits),
                    FloatText(CentreY, CentreDigits),
                    FloatText(Zoom, 4), MaxIter, Ms, ThreadCount, Warn]);
  if Length(Result) > Width then
    SetLength(Result, Width)
  else
    Result := Result + StringOfChar(' ', Width - Length(Result));
end;

procedure DrawInteractive;
var
  Start, Ms: QWord;
  Frame: string;
  K: Integer;
begin
  Start := GetTickCount64;
  RenderFrame;
  Ms := GetTickCount64 - Start;

  Frame := '';
  for K := 0 to Rows - 1 do
    Frame := Frame + Esc + '[' + IntToStr(K + 1) + ';1H' + Lines[K];
  Frame := Frame + Esc + '[' + IntToStr(Rows + 1) + ';1H' + Esc + '[7m'
           + StatusLine(Ms) + Esc + '[0m';
  WriteOut(Frame);
end;

{ Work out the picture size from the arguments and terminal. Returns True
  if it changed since the last call. }
function UpdateSize: Boolean;
var
  Cols, TermRows, NewW, NewR: Integer;
begin
  if not TerminalSize(Cols, TermRows) then
  begin
    Cols := 120;
    TermRows := 41;
  end;
  NewW := Cols;
  NewR := TermRows - 1;             { last row is the status line }
  if ArgWidth > 0 then NewW := Min(ArgWidth, NewW);
  if ArgRows > 0 then NewR := Min(ArgRows, NewR);
  NewW := Max(2, NewW);
  NewR := Max(1, NewR);
  Result := (NewW <> Width) or (NewR <> Rows);
  Width := NewW;
  Rows := NewR;
end;

{ Apply the keys in Buf. Returns True if the view changed. }
function HandleKeys(const Buf: array of Byte; N: Integer): Boolean;
var
  K: Integer;
  C: Char;
  Arrow: Char;
  Changed: Boolean;

  procedure Pan(DX, DY: Double);
  begin
    CentreX := CentreX + DX * SpanX * PanStep;
    CentreY := CentreY + DY * SpanY * PanStep;
    Changed := True;
  end;

begin
  Changed := False;
  K := 0;
  while K < N do
  begin
    C := Chr(Buf[K]);
    Arrow := #0;

    if C = Esc then
    begin
      { ESC [ A..D or ESC O A..D are arrow keys; a lone ESC means quit }
      if (K + 2 < N) and (Chr(Buf[K + 1]) in ['[', 'O']) then
      begin
        Arrow := Chr(Buf[K + 2]);
        Inc(K, 2);
        { Skip the rest of any longer sequence, e.g. ESC [ 1 ; 5 A }
        while (K < N) and not (Chr(Buf[K]) in ['A'..'Z', 'a'..'z', '~']) do
        begin
          Inc(K);
          if K < N then Arrow := Chr(Buf[K]);
        end;
      end
      else if K + 1 >= N then
        QuitRequested := True;
    end
    else
      case C of
        'h': Arrow := 'D';
        'j': Arrow := 'B';
        'k': Arrow := 'A';
        'l': Arrow := 'C';
        '+', '=':
          begin Zoom := Zoom * ZoomStep; Changed := True; end;
        '-', '_':
          begin Zoom := Max(Zoom / ZoomStep, 0.1); Changed := True; end;
        ']':
          begin
            MaxIter := Min(Round(MaxIter * IterStep), MaxIterLimit);
            Changed := True;
          end;
        '[':
          begin
            MaxIter := Max(Round(MaxIter / IterStep), MinIter);
            Changed := True;
          end;
        'r', 'R':
          begin
            CentreX := DefaultCX; CentreY := DefaultCY; Zoom := 1;
            MaxIter := DefaultIter;
            Changed := True;
          end;
        'q', 'Q', #3, #4:
          QuitRequested := True;
      end;

    case Arrow of
      'A': Pan(0, 1);
      'B': Pan(0, -1);
      'C': Pan(1, 0);
      'D': Pan(-1, 0);
    end;
    Inc(K);
  end;
  Result := Changed;
end;

procedure RunInteractive;
var
  Buf: array[0..255] of Byte;
  N: TsSize;
  Dirty: Boolean;
begin
  fpSignal(SIGTERM, @OnSignal);
  fpSignal(SIGHUP, @OnSignal);
  fpSignal(SIGINT, @OnSignal);

  EnterRawMode;
  try
    Width := 0;
    Rows := 0;
    Dirty := True;
    while not QuitRequested do
    begin
      if UpdateSize then
      begin
        WriteOut(Esc + '[0m' + Esc + '[2J');
        Dirty := True;
      end;
      if Dirty then
        DrawInteractive;

      { Wait up to VTIME for input, then take everything queued, so held
        keys are applied together instead of lagging behind }
      N := fpRead(0, Buf, SizeOf(Buf));
      Dirty := (N > 0) and HandleKeys(Buf, N);
    end;
  finally
    LeaveRawMode;
  end;

  WriteLn('View: ./', ExtractFileName(ParamStr(0)), ' ', ArgWidth, ' ', ArgRows,
          ' ', MaxIter, ' ', FloatText(CentreX, CentreDigits), ' ',
          FloatText(CentreY, CentreDigits), ' ', FloatText(Zoom, 6));
end;

procedure RunOnce;
var
  K: Integer;
begin
  Width := ArgWidth;
  Rows := ArgRows;
  if Width <= 0 then Width := 120;
  if Rows <= 0 then Rows := 40;
  Width := Max(2, Width);
  Rows := Max(1, Rows);
  RenderFrame;
  for K := 0 to Rows - 1 do
    WriteLn(Lines[K]);
end;

procedure ShowHelp;
var
  Prog: string;
begin
  Prog := ExtractFileName(ParamStr(0));
  WriteLn('Usage: ', Prog, ' [width] [rows] [max_iter] [centre_x] [centre_y] [zoom]');
  WriteLn;
  WriteLn('Explore the Mandelbrot set interactively using truecolor half blocks.');
  WriteLn('Arguments are positional; omit trailing ones to use their defaults.');
  WriteLn;
  WriteLn('  width     terminal columns; 0 = fit the terminal  (default 0)');
  WriteLn('  rows      terminal rows; 0 = fit the terminal     (default 0)');
  WriteLn('  max_iter  iteration limit                         (default 500)');
  WriteLn('  centre_x  real part of the view centre            (default -0.75)');
  WriteLn('  centre_y  imaginary part of the view centre       (default 0)');
  WriteLn('  zoom      magnification; 1 shows the whole set    (default 1)');
  WriteLn;
  WriteLn('Keys:');
  WriteLn('  arrows, h j k l   pan');
  WriteLn('  + or =            zoom in');
  WriteLn('  - or _            zoom out');
  WriteLn('  ]                 more iterations');
  WriteLn('  [                 fewer iterations');
  WriteLn('  r                 reset the view');
  WriteLn('  q, Esc, Ctrl-C    quit and print the command for the current view');
  WriteLn;
  WriteLn('Options:');
  WriteLn('  -h, --help  show this help and exit');
  WriteLn;
  WriteLn('When output is not a terminal, one frame is drawn (120x40 by default).');
  WriteLn('Uses every CPU core; set MANDELBROT_THREADS to change the thread count.');
  WriteLn;
  WriteLn('Examples:');
  WriteLn('  ', Prog, '                                  explore from the whole set');
  WriteLn('  ', Prog, ' 0 0 2000 -0.7436 0.1318 200      start in Seahorse Valley');
  WriteLn('  ', Prog, ' 160 50 3000 -0.1011 0.9563 300 > view.ans     save one frame');
  WriteLn;
  WriteLn('Needs a truecolor terminal with a Unicode font (kitty, alacritty, ...).');
end;

begin
  for I := 1 to ParamCount do
    if (ParamStr(I) = '-h') or (ParamStr(I) = '--help') then
    begin
      ShowHelp;
      Halt(0);
    end;

  FS := DefaultFormatSettings;
  FS.DecimalSeparator := '.';

  ArgWidth := Max(0, IntArg(1, 0));
  ArgRows  := Max(0, IntArg(2, 0));
  MaxIter  := EnsureRange(IntArg(3, DefaultIter), 2, MaxIterLimit);
  CentreX  := FloatArg(4, DefaultCX);
  CentreY  := FloatArg(5, DefaultCY);
  Zoom     := FloatArg(6, 1.0);
  if Zoom <= 0 then Zoom := 1.0;

  ThreadCount := DetectThreads;
  StartPool;
  try
    if (IsATTY(0) = 1) and (IsATTY(1) = 1) then
      RunInteractive
    else
      RunOnce;
  finally
    StopPool;
  end;
end.
