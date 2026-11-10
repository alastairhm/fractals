# To do

Ideas for what to build next, roughly in priority order.

## Mouse support (new mandelbrot6)

- Click to centre and zoom in on a point, right-click to zoom out, scroll
  wheel to zoom around the cursor.
- Turn on SGR mouse reporting (`ESC[?1000h` + `ESC[?1006h`) in
  `EnterRawMode`, turn it off in `LeaveRawMode`, and parse
  `ESC [ < b ; x ; y M/m` in `HandleKeys`.
- Each cell is two pixels tall, so a click maps to an exact point on the
  complex plane.

## Julia set mode

- `j` toggles between the Mandelbrot set and the Julia set for the point at
  the centre of the view.
- Only the inner loop changes: *z* starts at the pixel and *c* is held
  fixed. The cardioid/bulb shortcut must be skipped in Julia mode.
- **Decided:** mouse support and Julia mode go in a new `mandelbrot6.pas`,
  started from a copy of `mandelbrot5.pas`, keeping the
  one-step-per-program pattern. Leave `mandelbrot5` as it is.

## Deeper zoom

- Double precision runs out around zoom 10¹³ (the status line warns about
  this).
- Easy: switch the pixel maths to `Extended` (80-bit on x86-64) for about
  1000× more depth, at some speed cost.
- Hard: perturbation theory, with one high-precision reference orbit and
  per-pixel deltas in doubles, for zooms of 10¹⁰⁰ and beyond.

## Faster interior

- Periodicity checking: stop iterating once the orbit repeats (Brent-style
  check against a saved *z*). Big win for interior pixels at high
  `max_iter`.
- Needs care at deep zoom so boundary pixels aren't wrongly marked inside.
  `make check` will catch any change to the output.

## Smaller jobs

- Palette switching with a key (cycle a few gradient presets).
- Bookmarks: a list of saved views to jump between.
- Write the view's coordinates next to each saved PNG (a `.txt` sidecar
  or PNG text metadata), so a picture can be reopened as a view.
- GitHub Actions workflow: install `fpc`, then `make && make check`.
- Make `mandelbrot4` fit the terminal size by default, like `mandelbrot5`.
- README: the `mandelbrot4` example `-0.1011 0.9563` is labelled "spiral
  near the top bulb", but it shows branching filaments.
