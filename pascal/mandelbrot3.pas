program Mandelbrot3;

{ Coloured ASCII Mandelbrot renderer (24-bit ANSI "truecolor").
  Builds on mandelbrot2.pas:
    - uses a smooth (fractional) escape count so colours blend continuously
      instead of stepping in bands;
    - each character is drawn in a colour from a cosine gradient;
    - colour escape codes are only emitted when the colour changes.

  Needs a truecolor terminal (kitty, alacritty, foot, wezterm, ...).

  Build:  fpc -O2 mandelbrot3.pas
  Run:    ./mandelbrot3 [width] [height] [max_iterations]
          (-h or --help for usage) }

{$mode objfpc}{$H+}

uses
  SysUtils, Math;

const
  Palette = ' .:-=+*#%';
  InsideChar = '@';
  XMin = -2.5;
  XMax = 1.0;
  YMin = -1.2;
  YMax = 1.2;
  { A large bailout radius makes the smooth escape count accurate }
  Bailout2 = 256.0 * 256.0;
  Esc = #27;

type
  TRGB = record
    R, G, B: Byte;
  end;

var
  Width, Height, MaxIter: Integer;
  Row, Col, Iter, Idx: Integer;
  Cx, Cy, Zx, Zy, Zx2, Zy2, Smooth, T, LogMax: Double;
  Colour, Last: TRGB;
  HaveLast: Boolean;
  Line: string;

function ArgOr(Index, Default: Integer): Integer;
begin
  if ParamCount >= Index then
    Result := StrToIntDef(ParamStr(Index), Default)
  else
    Result := Default;
end;

function HelpRequested: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if (ParamStr(I) = '-h') or (ParamStr(I) = '--help') then
      Exit(True);
end;

procedure ShowHelp;
var
  Prog: string;
begin
  Prog := ExtractFileName(ParamStr(0));
  WriteLn('Usage: ', Prog, ' [width] [height] [max_iterations]');
  WriteLn;
  WriteLn('Render the Mandelbrot set as coloured ASCII art using');
  WriteLn('24-bit ANSI colour. Needs a truecolor terminal.');
  WriteLn('Arguments are positional; omit trailing ones to use their defaults.');
  WriteLn;
  WriteLn('  width           output columns       (default 100)');
  WriteLn('  height          output rows          (default 40)');
  WriteLn('  max_iterations  iteration limit      (default 200)');
  WriteLn;
  WriteLn('Options:');
  WriteLn('  -h, --help  show this help and exit');
  WriteLn;
  WriteLn('Example:');
  WriteLn('  ', Prog, ' 160 50 500');
end;

function RGB(R, G, B: Byte): TRGB;
begin
  Result.R := R; Result.G := G; Result.B := B;
end;

{ Cosine gradient (after Inigo Quilez): T in 0..1 -> deep blue, through
  cyan and white, to orange. Only ~65% of the cosine cycle is used so the
  edge of the set (T near 1) is bright rather than wrapping back to blue. }
function Gradient(T: Double): TRGB;

  function Chan(Phase: Double): Byte;
  begin
    Result := Round(255 * (0.5 + 0.5 * Cos(2 * Pi * (T + Phase))));
  end;

begin
  T := T * 0.65;
  Result := RGB(Chan(0.50), Chan(0.60), Chan(0.75));
end;

function SameRGB(const A, B: TRGB): Boolean;
begin
  Result := (A.R = B.R) and (A.G = B.G) and (A.B = B.B);
end;

begin
  if HelpRequested then
  begin
    ShowHelp;
    Halt(0);
  end;

  Width   := Max(2, ArgOr(1, 100));
  Height  := Max(2, ArgOr(2, 40));
  MaxIter := Max(2, ArgOr(3, 200));
  LogMax  := Ln(MaxIter);
  Last    := RGB(0, 0, 0);

  for Row := 0 to Height - 1 do
  begin
    Cy := YMax - Row * (YMax - YMin) / (Height - 1);
    Line := '';
    HaveLast := False;

    for Col := 0 to Width - 1 do
    begin
      Cx := XMin + Col * (XMax - XMin) / (Width - 1);

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
      begin
        Colour := RGB(70, 30, 90);   { dim purple interior }
        Idx := 0;
      end
      else
      begin
        { Fractional escape count: Iter + 1 - log2(log|z|) }
        Smooth := Iter + 1 - Ln(0.5 * Ln(Zx2 + Zy2)) / Ln(2);
        T := EnsureRange(Ln(Max(Smooth, 1.0)) / LogMax, 0.0, 0.999);
        Colour := Gradient(T);
        Idx := 1 + Trunc(T * Length(Palette));
      end;

      if (not HaveLast) or (not SameRGB(Colour, Last)) then
      begin
        Line := Line + Format('%s[38;2;%d;%d;%dm',
                              [Esc, Colour.R, Colour.G, Colour.B]);
        Last := Colour;
        HaveLast := True;
      end;

      if Idx = 0 then
        Line := Line + InsideChar
      else
        Line := Line + Palette[Idx];
    end;

    WriteLn(Line, Esc, '[0m');   { reset colour at end of each row }
  end;
end.
