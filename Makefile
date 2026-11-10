# Build the Mandelbrot renderers with Free Pascal.
#
#   make              build every program
#   make mandelbrot4  build one program
#   make check        smoke tests (see below)
#   make screenshots  regenerate screenshots/*.png (needs python-pillow)
#   make clean        remove binaries and build output

FPC      ?= fpc
# -v0ew: errors and warnings only, -l-: no banner. mandelbrot5 links libc
# for threading, so it always prints two harmless crtbeginS.o / crtendS.o
# warnings.
FPCFLAGS ?= -O2 -v0ew -l-

PROGRAMS := $(sort $(basename $(wildcard mandelbrot*.pas)))

# Views where piped mandelbrot5 output must match mandelbrot4 byte for byte
CHECK_VIEWS := "120 36 1000" \
               "120 36 2000 -0.7436 0.1318 200" \
               "160 50 3000 -0.1011 0.9563 300" \
               "1 1" "2 1 2" "x y z" "3 2 5 0 0 -4"

.PHONY: all check screenshots clean

all: $(PROGRAMS)

$(PROGRAMS): %: %.pas
	$(FPC) $(FPCFLAGS) $<

# Every program: --help works, and the smallest sizes don't crash.
# mandelbrot5 piped: identical to mandelbrot4 for each of CHECK_VIEWS.
check: all
	@set -e; tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT; \
	for p in $(PROGRAMS); do \
	    ./$$p --help > /dev/null; \
	    ./$$p 1 1 > /dev/null; \
	    echo "ok   $$p: --help, 1x1"; \
	done; \
	for v in $(CHECK_VIEWS); do \
	    ./mandelbrot4 $$v > "$$tmp/4"; \
	    ./mandelbrot5 $$v > "$$tmp/5"; \
	    if cmp -s "$$tmp/4" "$$tmp/5"; then \
	        echo "ok   mandelbrot5 == mandelbrot4: $$v"; \
	    else \
	        echo "FAIL mandelbrot5 != mandelbrot4: $$v"; exit 1; \
	    fi; \
	done

screenshots:
	tools/screenshots.sh

clean:
	rm -f $(PROGRAMS) *.o *.ppu link*.res ppas.sh
