"""Diffraction grating example"""

import dtmm
import numpy as np
import matplotlib.pyplot as plt
# Change matplotlib backend to an interactive one
import matplotlib
matplotlib.use("TkAgg")

#: pixel size in nm
PIXELSIZE = 100
#: compute box dimensions
NLAYERS, HEIGHT, WIDTH = 10, 1024,1024
#: illumination wavelengths in nm
WAVELENGTHS = np.linspace(380,780,9)
#: dummy data..
d, e, a = dtmm.nematic_droplet_data((NLAYERS, HEIGHT, WIDTH), 
          radius = 3000, profile = "x", no = 1.5, ne = 1.5, nhost = 1.5)

d[...]=1

a[...] = 0.
a[...,1] = np.pi/2

e=e + 1j
mod = (1 + 1*np.sin(np.linspace(0,np.pi/2048*PIXELSIZE*WIDTH, WIDTH))**2)
e[...,2] = mod[None,None,:]

window = dtmm.aperture((HEIGHT,WIDTH), 0.1,1)


#: create non-polarized input light
field_data_in = dtmm.illumination_data((HEIGHT, WIDTH), WAVELENGTHS, jones = (1,0),
                                            pixelsize = PIXELSIZE, window = window) 
#: transfer input light through stack
f,w,p = dtmm.transfer_field(field_data_in, (d,e,a), betamax = np.inf, diffraction = 1)

ff = np.fft.fftshift(dtmm.fft.fft2(f),axes = (-2,-1))
i = dtmm.field2specter(ff)
cmf = dtmm.load_tcmf(w)
c = dtmm.specter2color(i,cmf, norm = True)
plt.imshow(c)
plt.title("far field - fft of the near field")


#: visualize output field
viewer1 = dtmm.field_viewer((f,w,p), betamax = 1)
viewer1.set_parameters(sample = 0, intensity = 2,
                polarizer = None, focus = 0, analyzer = 0)

fig, ax = viewer1.plot(fmax = 1000)
ax.set_title("near field")
fig.show()
