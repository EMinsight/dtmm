"""Hello nematic droplet example."""

import dtmm
import numpy as np

#: pixel size in nm
PIXELSIZE = 200
#: compute box dimensions
NLAYERS, HEIGHT, WIDTH = 60, 96,96
#: illumination wavelengths in nm
WAVELENGTHS = np.linspace(380,780,9)
#: create some experimental data (stack)
optical_data = [dtmm.nematic_droplet_data((NLAYERS, HEIGHT, WIDTH), 
          radius = 30, profile = "r", no = 1.5, ne = 1.6, nhost = 1.5)]

#: create non-polarized input light
field_data_in = dtmm.illumination_data((HEIGHT, WIDTH), WAVELENGTHS, 
                                            pixelsize = PIXELSIZE) 
#: transfer input light through stack
field_data_out = dtmm.transfer_field(field_data_in, optical_data, diffraction = 0, betamax = 1)

#: visualize output field
# no diffraction to simulate output of standard jones method
viewer1 = dtmm.field_viewer(field_data_out, diffraction = False) 
viewer1.set_parameters(sample = 0, intensity = 2,
                polarizer = 0, analyzer = 90)
fig,ax = viewer1.plot()
ax.set_title("diffraction = 0")


field_data_out = dtmm.transfer_field(field_data_in, optical_data, diffraction = 1, betamax = 1)



viewer2 = dtmm.field_viewer(field_data_out)
viewer2.set_parameters(sample = 0, intensity = 2,
                polarizer = 0, focus = -14, analyzer = 90)

fig,ax = viewer2.plot()
ax.set_title("diffraction = 1")

import os
on_rtd = os.environ.get('READTHEDOCS') == 'True'
if on_rtd:
    #limited memory on RTD server requires split diffraction calculation
    SPLITDIFF = True
else:
    SPLITDIFF = False

field_data_out = dtmm.transfer_field(field_data_in, optical_data, diffraction = 5, betamax = 1,  split_diffraction = SPLITDIFF)

viewer3 = dtmm.field_viewer(field_data_out)
viewer3.set_parameters(sample = 0, intensity = 2,
                polarizer = 0, focus = -14, analyzer = 90)


fig,ax = viewer3.plot()
ax.set_title("diffraction = 5")


