program Mandelbrot;

{ Basic ASCII Mandelbrot set renderer for the terminal.
  Build:  fpc -O2 mandelbrot.pas
  Run:    ./mandelbrot [width] [height] [max_iterations]
          (-h or --help for usage) }

{$mode objfpc}{$H+}

uses
  SysUtils, Math;

const
  { Characters from "escapes fast" to "escapes slowly" }
  Palette = ' .:-=+*#%@';
  XMin = -2.5;
  XMax = 1.0;
  YMin = -1.2;
  YMax = 1.2;

var
  Width, Height, MaxIter: Integer;
  Row, Col, Iter, Idx: Integer;
  Cx, Cy, Zx, Zy, Zx2, Zy2: Double;
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
  WriteLn('Render the Mandelbrot set as plain ASCII art.');
  WriteLn('Characters cycle through a 10-step palette by escape count.');
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

begin
  if HelpRequested then
  begin
    ShowHelp;
    Halt(0);
  end;

  { At least 2 columns/rows so the (Width - 1) and (Height - 1) scaling
    never divides by zero, and at least 2 iterations so escape is possible. }
  Width   := Max(2, ArgOr(1, 100));
  Height  := Max(2, ArgOr(2, 40));
  MaxIter := Max(2, ArgOr(3, 200));

  for Row := 0 to Height - 1 do
  begin
    Cy := YMax - Row * (YMax - YMin) / (Height - 1);
    SetLength(Line, Width);

    for Col := 0 to Width - 1 do
    begin
      Cx := XMin + Col * (XMax - XMin) / (Width - 1);

      { Iterate z := z^2 + c until |z| > 2 or we hit MaxIter }
      Zx := 0; Zy := 0; Zx2 := 0; Zy2 := 0;
      Iter := 0;
      while (Zx2 + Zy2 <= 4.0) and (Iter < MaxIter) do
      begin
        Zy  := 2 * Zx * Zy + Cy;
        Zx  := Zx2 - Zy2 + Cx;
        Zx2 := Zx * Zx;
        Zy2 := Zy * Zy;
        Inc(Iter);
      end;

      if Iter = MaxIter then
        Line[Col + 1] := '@'   { inside the set }
      else
      begin
        Idx := (Iter mod (Length(Palette) - 1)) + 1;
        Line[Col + 1] := Palette[Idx];
      end;
    end;

    WriteLn(Line);
  end;
end.
