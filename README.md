# spyce-nvaders
A midway space invaders arcade emulator made with python.

## controls
- left, right arrow keys - P1 move
- left ctrl - P1 shoot
- a, d - P2 move
- space - P2 shoot
- return - 1P start
- backspace - 2P start
- c - insert credit
- esc - quit

## why?
this was a bad idea, python is *really* slow for making an interpreted emulator, there are probably a lot of optimizations that can be done to make it playable at 100% speed, one of which could be using numpy arrays for the memory, or, at the very least, for the video memory, as the biggest bottleneck is the `rasterize` method, perhaps multi-processing could help a lot with this as well.

another reason for why this was a bad idea is that handling hexadecimal / bytes in python is a PITA, as they are automatically converted to ints.

## todo (?)
this repo probably won't see much action as I plan on making other emulators (in another language ofc...), but if I ever come back to it, here are the things that are left to do:

- [ ] Try multi-processing
- [ ] Cleanup code (structure)
- [ ] Colorize
- [ ] Implement sound
