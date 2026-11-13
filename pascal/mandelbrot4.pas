program Mandelbrot4;

{ Half-block truecolor Mandelbrot renderer.
  Each terminal cell shows two vertically stacked pixels using the upper
  half block character U+2580: the foreground colour paints the top pixel,
  the background colour paints the bottom one. Terminal cells are about
  twice as tall as wide, so these pixels are roughly square.

  Colouring uses the smooth escape count from mandelbrot3.pas, but in two
  passes: every pixel is computed first, then the gradient is stretched
  between the lowest and highest values actually in view. That keeps full
  contrast at any zoom level. The interior is black.

  Needs a truecolor terminal with a Unicode font (kitty, alacritty, ...).

  Build:  fpc -O2 mandelbrot4.pas
  Run:    ./mandelbrot4 [width] [rows] [max_iter] [centre_x] [centre_y] [zoom]

    width     terminal columns           (default 120)
    rows      terminal rows; pixel height is 2 * rows   (default 40)
    max_iter  iteration limit            (default 500)
    centre_x  real part of view centre   (default -0.75)
    centre_y  imag part of view centre   (default 0)
    zoom      magnification; 1 shows the whole set     (default 1)

  Run with -h or --help for usage.

  Try:  ./mandelbrot4 160 50 2000 -0.7436 0.1318 200 }

{$mode objfpc}{$H+}
{$codepage utf8}

uses
  SysUtils, Math;

const
  Esc = #27;
  HalfBlock = #$E2#$96#$80;         { U+2580 UPPER HALF BLOCK, UTF-8 bytes }
  Bailout2 = 256.0 * 256.0;
  BaseSpan = 3.5;                   { real-axis width shown at zoom 1 }

type
  TRGB = record
    R, G, B: Byte;
  end;

var
  Width, Rows, MaxIter: Integer;
  CentreX, CentreY, Zoom: Double;
  SpanX, SpanY, X0, Y0, PixelSize: Double;
  Row, Col, I: Integer;
  Values: array of Double;          { log smooth count per pixel, -1 = inside }
  VMin, VMax, VRange: Double;
  Top, Bottom, LastFg, LastBg: TRGB;
  HaveLast: Boolean;
  Line: string;

function IntArg(Index, Default: Integer): Integer;
begin
  if ParamCount >= Index then
    Result := StrToIntDef(ParamStr(Index), Default)
  else
    Result := Default;
end;

function FloatArg(Index: Integer; Default: Double): Double;
var
  FS: TFormatSettings;
begin
  FS := DefaultFormatSettings;
  FS.DecimalSeparator := '.';     { accept "0.25" whatever the locale }
  if ParamCount >= Index then
    Result := StrToFloatDef(ParamStr(Index), Default, FS)
  else
    Result := Default;
end;

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
  Cx, Cy, Zx, Zy, Zx2, Zy2, Smooth: Double;
  Iter: Integer;
begin
  Cx := X0 + (Px + 0.5) * PixelSize;
  Cy := Y0 - (Py + 0.5) * PixelSize;

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

{ Colour for pixel (Px, Py) from the precomputed values }
function PixelColour(Px, Py: Integer): TRGB;
var
  V: Double;
begin
  V := Values[Py * Width + Px];
  if V < 0 then
    Exit(RGB(0, 0, 0));
  Result := Gradient((V - VMin) / VRange);
end;

procedure ShowHelp;
var
  Prog: string;
begin
  Prog := ExtractFileName(ParamStr(0));
  WriteLn('Usage: ', Prog, ' [width] [rows] [max_iter] [centre_x] [centre_y] [zoom]');
  WriteLn;
  WriteLn('Render the Mandelbrot set in the terminal using truecolor half blocks.');
  WriteLn('Arguments are positional; omit trailing ones to use their defaults.');
  WriteLn;
  WriteLn('  width     terminal columns                        (default 120)');
  WriteLn('  rows      terminal rows; pixel height is 2*rows   (default 40)');
  WriteLn('  max_iter  iteration limit                         (default 500)');
  WriteLn('  centre_x  real part of the view centre            (default -0.75)');
  WriteLn('  centre_y  imaginary part of the view centre       (default 0)');
  WriteLn('  zoom      magnification; 1 shows the whole set    (default 1)');
  WriteLn;
  WriteLn('Options:');
  WriteLn('  -h, --help  show this help and exit');
  WriteLn;
  WriteLn('Examples:');
  WriteLn('  ', Prog, ' $(tput cols) $(($(tput lines)-1)) 1000    fill the terminal');
  WriteLn('  ', Prog, ' 160 50 2000 -0.7436 0.1318 200            Seahorse Valley');
  WriteLn('  ', Prog, ' 160 50 3000 -0.1011 0.9563 300            spiral near top bulb');
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

  Width   := Max(2, IntArg(1, 120));
  Rows    := Max(1, IntArg(2, 40));
  MaxIter := Max(2, IntArg(3, 500));
  CentreX := FloatArg(4, -0.75);
  CentreY := FloatArg(5, 0.0);
  Zoom    := FloatArg(6, 1.0);
  if Zoom <= 0 then Zoom := 1.0;

  { Square pixels: the vertical span follows from the width and row count }
  SpanX := BaseSpan / Zoom;
  PixelSize := SpanX / Width;
  SpanY := PixelSize * Rows * 2;
  X0 := CentreX - SpanX / 2;
  Y0 := CentreY + SpanY / 2;

  { Pass 1: compute every pixel and find the range of values in view }
  SetLength(Values, Width * Rows * 2);
  VMin := MaxDouble;
  VMax := -1;
  for I := 0 to High(Values) do
  begin
    Values[I] := PixelValue(I mod Width, I div Width);
    if Values[I] >= 0 then
    begin
      VMin := Min(VMin, Values[I]);
      VMax := Max(VMax, Values[I]);
    end;
  end;
  VRange := Max(VMax - VMin, 1e-9);

  { Pass 2: draw }
  LastFg := RGB(0, 0, 0);
  LastBg := RGB(0, 0, 0);

  for Row := 0 to Rows - 1 do
  begin
    Line := '';
    HaveLast := False;

    for Col := 0 to Width - 1 do
    begin
      Top    := PixelColour(Col, Row * 2);
      Bottom := PixelColour(Col, Row * 2 + 1);

      { Only emit colour codes that actually changed }
      if (not HaveLast) or (not SameRGB(Top, LastFg)) then
        Line := Line + Format('%s[38;2;%d;%d;%dm', [Esc, Top.R, Top.G, Top.B]);
      if (not HaveLast) or (not SameRGB(Bottom, LastBg)) then
        Line := Line + Format('%s[48;2;%d;%d;%dm',
                              [Esc, Bottom.R, Bottom.G, Bottom.B]);
      LastFg := Top;
      LastBg := Bottom;
      HaveLast := True;

      Line := Line + HalfBlock;
    end;

    WriteLn(Line, Esc, '[0m');
  end;
end.
