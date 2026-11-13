program Mandelbrot2;

{ ASCII Mandelbrot renderer with a smooth gradient.
  Unlike mandelbrot.pas, the escape count is scaled across the palette
  (logarithmically) instead of wrapped with mod, and the interior uses its
  own character, so the edge of the set shades smoothly into it.

  Build:  fpc -O2 mandelbrot2.pas
  Run:    ./mandelbrot2 [width] [height] [max_iterations]
          (-h or --help for usage) }

{$mode objfpc}{$H+}

uses
  SysUtils, Math;

const
  { Outside points, from "escapes fast" to "escapes slowly" }
  Palette = ' .:-=+*#%';
  InsideChar = '@';
  XMin = -2.5;
  XMax = 1.0;
  YMin = -1.2;
  YMax = 1.2;

var
  Width, Height, MaxIter: Integer;
  Row, Col, Iter, Idx: Integer;
  Cx, Cy, Zx, Zy, Zx2, Zy2, LogMax: Double;
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
  WriteLn('Render the Mandelbrot set as ASCII art with a smooth');
  WriteLn('(log-scaled) character gradient.');
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

  Width   := Max(2, ArgOr(1, 100));
  Height  := Max(2, ArgOr(2, 40));
  MaxIter := Max(2, ArgOr(3, 200));
  LogMax  := Ln(MaxIter);

  for Row := 0 to Height - 1 do
  begin
    Cy := YMax - Row * (YMax - YMin) / (Height - 1);
    SetLength(Line, Width);

    for Col := 0 to Width - 1 do
    begin
      Cx := XMin + Col * (XMax - XMin) / (Width - 1);

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

      if Iter >= MaxIter then
        Line[Col + 1] := InsideChar
      else
      begin
        { Iter is in 1..MaxIter-1; log scale maps it to 0..<1, then
          stretch that across the palette. }
        Idx := 1 + Trunc(Ln(Iter) / LogMax * Length(Palette));
        Line[Col + 1] := Palette[Min(Idx, Length(Palette))];
      end;
    end;

    WriteLn(Line);
  end;
end.
