"""
Director and optical data creation and IO functions.
"""

from __future__ import absolute_import, print_function, division

import numpy as np
import numba
import sys

from dtmm.conf import FDTYPE, CDTYPE, NFDTYPE, NCDTYPE, NUMBA_CACHE,\
    NF32DTYPE, NF64DTYPE, NC128DTYPE, NC64DTYPE, DTMMConfig
from dtmm.rotation import rotation_matrix_x, rotation_matrix_y, rotation_matrix_z, rotate_vector


def read_director(file, shape, dtype=FDTYPE, sep="", endian=sys.byteorder, order="zyxn", nvec="xyz"):
    """
    Reads raw director data from a binary or text file.
    
    A convenient way to read director data from file.
    
    Parameters
    ----------
    file : str or file
        Open file object or filename.
    shape : sequence of ints
        Shape of the data array, e.g., ``(50, 24, 34, 3)``
    dtype : data-type
        Data type of the raw data. It is used to determine the size of the items 
        in the file.
    sep : str
        Separator between items if file is a text file.
        Empty ("") separator means the file should be treated as binary.
        Spaces (" ") in the separator match zero or more whitespace characters.
        A separator consisting only of spaces must match at least one
        whitespace.
    endian : str, optional
        Endianess of the data in file, e.g. 'little' or 'big'. If endian is 
        specified and it is different than sys.endian, data is byteswapped. 
        By default no byteswapping is done. 
    order : str, optional
        Data order. It can be any permutation of 'xyzn'. Defaults to 'zyxn'. It
        describes what are the meaning of axes in data.
    nvec : str, optional
        Order of the director data coordinates. Any permutation of 'x', 'y' and 
        'z', e.g. 'yxz', 'zxy' ...

    Returns
    -------
    director : np.ndarray
        The director field in order <order>
    """
    if len(list(shape)) != 4:
        raise TypeError("shape must be director data shape (z,x,y,n)")

    # Read raw data from file
    data = read_raw(file, shape, dtype, sep=sep, endian=endian)

    # Covert raw data into director representation
    director = raw2director(data, order, nvec)

    return director


def rotate_director(rotation_matrix, data, method="linear", fill_value=(0., 0., 0.), normalize=True, out=None):
    """
    Rotate a director field around the center of the compute box by a specified
    rotation matrix. This rotation is lossy, as datapoints are interpolated.
    The shape of the output remains the same.

    Parameters
    ----------
    rotation_matrix : array_like
        A 3x3 rotation matrix.
    data: array_like
        Array specifying director field with ndim = 4
    method : str
        Interpolation method "linear" or "nearest"
    fill_value : numbers, optional
        If provided, the values (length 3 vector) to use for points outside of the
        interpolation domain. Defaults to (0.,0.,0.).
    normalize : bool,
        Whether to normalize the length of the director to 1. after rotation
        (interpolation) is performed. Because of interpolation error, the length
        of the director changes slightly, and this options adds a constant
        length constraint to reduce the error.
    out : ndarray, optional
        Output array.

    Returns
    -------
    y : np.ndarray
        A rotated director field

    See Also
    --------
    data.rot90_director : a lossless rotation by 90 degrees.

    """

    from scipy.interpolate import RegularGridInterpolator

    # Log the rotation
    if DTMMConfig.verbose > 0:
        print("Rotating director.")

    # Preallocate output
    out = np.empty_like(data)

    # Size of each direction and number of components
    nz, ny, nx, nv = data.shape

    shape = (nz, ny, nx)
    az, ay, ax = [np.arange(-l / 2. + .5, l / 2. + .5) for l in shape]

    fillx, filly, fillz = fill_value
    xdir = RegularGridInterpolator((az, ay, ax), data[..., 0],
                                   fill_value=fillx, bounds_error=False, method=method)
    ydir = RegularGridInterpolator((az, ay, ax), data[..., 1],
                                   fill_value=filly, bounds_error=False, method=method)
    zdir = RegularGridInterpolator((az, ay, ax), data[..., 2],
                                   fill_value=fillz, bounds_error=False, method=method)

    zz, yy, xx = np.meshgrid(az, ay, ax, indexing="ij", copy=False, sparse=True)

    out[..., 0] = xx
    out[..., 1] = yy
    out[..., 2] = zz

    # Rotate the coordinate
    out = rotate_vector(rotation_matrix.T, out, out)

    # out2 = out.copy()
    # out2[...,0] = out[...,2]
    # out2[...,2] = out[...,0]

    # Reverse direction instead of copying
    out2 = out[..., ::-1]

    # Interpolate new director field
    xnew = xdir(out2)
    ynew = ydir(out2)
    znew = zdir(out2)

    out[..., 0] = xnew
    out[..., 1] = ynew
    out[..., 2] = znew

    # Rotate the vector in each voxel
    rotate_vector(rotation_matrix, out, out)

    if normalize:
        s = director2order(out)
        mask = (s == 0.)
        s[mask] = 1.
        return np.divide(out, s[..., None], out)
    else:
        return out


def rot90_director(data, axis="+x", out=None):
    """
    Rotate a director field by 90 degrees around the specified axis.

    Parameters
    ----------
    data: array_like
        Array specifying director field with ndim = 4.
    axis: str
        Axis around which to perform rotation. Can be in the form of
        '[s][n]X' where the optional parameter 's' can be "+" or "-" decribing
        the sign of rotation. [n] is an integer describing number of 90 degree
        rotations to perform, and 'X' is one of 'x', 'y' 'z', and defines
        rotation axis.
    out : ndarray, optional
        Output array.

    Returns
    -------
    y : ndarray
        A rotated director field

    See Also
    --------
    data.rotate_director : a general rotation for arbitrary angle.
    """
    # Convert numerical part of axis str into a number
    try:
        k = int(axis[:-1])
    except ValueError:
        k = int(axis[:-1] + "1")

    # Convert that number into an angle
    angle = np.pi / 2 * k

    # Grab axis name
    axis_name = axis[-1]

    # Create the rotation matrix
    if axis_name == "x":
        rotation_matrix = rotation_matrix_x(angle)
        axes = (1, 0)
    elif axis_name == "y":
        rotation_matrix = rotation_matrix_y(angle)
        axes = (0, 2)
    elif axis_name == "z":
        rotation_matrix = rotation_matrix_z(angle)
        axes = (2, 1)
    else:
        raise ValueError("Unknown axis type {}".format(axis_name))

    # Rotate the date points
    data_rot = np.rot90(data, k=k, axes=axes)
    # Rotate the director in each voxel then return
    return rotate_vector(rotation_matrix, data_rot, out)


def director2data(director, mask=None, no=1.5, ne=1.6, nhost=None,
                  thickness=None):
    """
    Builds optical data from director data. Director length is treated as
    an order parameter. Order parameter of S=1 means that refractive indices
    `no` and `ne` are set as the material parameters. With S!=1, a
    :func:`uniaxial_order` is used to calculate actual material parameters.

    Parameters
    ----------
    director : ndarray
        A 4D array describing the director
    mask : ndarray, optional
        If provided, this mask must be a 3D boolean mask that define voxels where
        nematic is present. This mask is used to define the nematic part of the sample.
        Volume not defined by the mask is treated as a host material. If mask is
        not provided, all data points are treated as a director.
    no : float
        Ordinary refractive index
    ne : float
        Extraordinary refractive index
    nhost : float
        Host refractive index (if mask is provided)
    thickness : ndarray
        Thickness of layers (in pixels). If not provided, this defaults to ones.

    Returns
    -------
    output : tuple[np.ndarray]

    """
    # Preallocate director
    material = np.empty(shape=director.shape, dtype=FDTYPE)
    # Convert indices of refraction into 3 dielectric constants at every point in space
    # [None,...] converts the (3,) array into a (1, 3) array
    material[...] = refind2eps([no, no, ne])[None, ...]
    # Adjusts dielectric constants to take into account uniaxial order
    material = uniaxial_order(director2order(director), material, out=material)

    # If mask is present, set everything outside the mask to the host dielectric constant
    if mask is not None:
        material[np.logical_not(mask), :] = refind2eps([nhost, nhost, nhost])[None, ...]

    # Generates default thickness if one is not provided
    if thickness is None:
        thickness = np.ones(shape=(material.shape[0],))

    # Convert the representation of the director from x,y,z lengths into angles
    angles = director2angles(director)

    return thickness, material, angles


def validate_optical_data(data, homogeneous=False):
    """
    Validates optical data.

    This function inspects validity of the optical data, and makes proper data
    conversions to match the optical data format. In case data is not valid and
    it cannot be converted to a valid data it raises an exception (ValueError).

    Parameters
    ----------
    data : tuple of optical data
        A valid optical data tuple.
    homogeneous : bool, optional
        Whether data is for a homogeneous layer. (Inhomogeneous by default)

    Returns
    -------
    data : tuple
        Validated optical data tuple.
    """
    # Split data tuple into it's parts
    thickness, material, angles = data
    # Convert thickness into numpy array
    thickness = np.asarray(thickness, dtype=FDTYPE)

    # Check thickness dimension
    if thickness.ndim == 0:
        # If (n,) convert to (1,n)
        thickness = thickness[None]
    elif thickness.ndim != 1:
        # If dimension is not (n,) or (1,n), return error
        raise ValueError("Thickness dimension should be 1.")

    # Number of layers
    n = len(thickness)

    # Covert material to numpy array
    material = np.asarray(material)

    # Convert material array to correct type
    if np.issubdtype(material.dtype, np.complexfloating):
        # Complex
        material = np.asarray(material, dtype=CDTYPE)
    else:
        # Real
        material = np.asarray(material, dtype=FDTYPE)

    if (material.ndim == 1 and homogeneous) or (material.ndim == 3 and not homogeneous):
        material = np.broadcast_to(material, (n,) + material.shape)
        # np.asarray([material for i in range(n)], dtype = material.dtype)

    # Ensure material is the same length as thickness
    if len(material) != n:
        raise ValueError("Material length should match thickness length")

    if (material.ndim != 2 and homogeneous) or (material.ndim != 4 and not homogeneous):
        raise ValueError("Invalid dimensions of the material.")

    # Convert angles to numpy array
    angles = np.asarray(angles, dtype=FDTYPE)

    if (angles.ndim == 1 and homogeneous) or (angles.ndim == 3 and not homogeneous):
        angles = np.broadcast_to(angles, (n,) + angles.shape)
        # angles = np.asarray([angles for i in range(n)], dtype = angles.dtype)

    # Ensure angles is of correct length
    if len(angles) != n:
        raise ValueError("Angles length should match thickness length")

    if (angles.ndim != 2 and homogeneous) or (angles.ndim != 4 and not homogeneous):
        raise ValueError("Invalid dimensions of the angles.")

    # Ensure material and angles have correct shape
    if material.shape != angles.shape:
        raise ValueError("Incompatible shapes for angles and material")

    # Return copies
    return thickness.copy(), material.copy(), angles.copy()


def raw2director(data, order="zyxn", nvec="xyz"):
    """
    Converts raw data to director array.

    Parameters
    ----------
    data : array
        Data array
    order : str, optional
        Data order. It can be any permutation of 'xyzn'. Defaults to 'zyxn'. It
        describes what are the meaning of axes in data.
    nvec : str, optional
        Order of the director data coordinates. Any permutation of 'x', 'y' and
        'z', e.g. 'yxz', 'zxy'. Defaults to 'xyz'

    Returns
    -------
    director : array
        A new array or same array (if no transposing and data copying was made)

    Example
    -------

    >>> a = np.random.randn(10,11,12,3)
    >>> director = raw2director(a, "xyzn")
    """
    # If not in zyxn order, then try to rearrange to correct order
    data = _reorder(data, order, "zyxn")

    # If nvec not in xyz order, then try to rearrange to correct order
    if nvec != "xyz":
        index = {"x": 0, "y": 1, "z": 2}
        out = np.empty_like(data)
        for i, idn in enumerate(nvec):
            j = index.pop(idn)
            out[..., j] = data[..., i]
        return out
    else:
        return data


def read_raw(file, shape, dtype, sep = "", endian = sys.byteorder):
    """Reads raw data from a binary or text file.
    
    Parameters
    ----------
    file : str or file
        Open file object or filename.
    shape : sequence of ints
        Shape of the data array, e.g., ``(50, 24, 34, 3)``
    dtype : data-type
        Data type of the raw data. It is used to determine the size of the items 
        in the file.
    sep : str
        Separator between items if file is a text file.
        Empty ("") separator means the file should be treated as binary.
        Spaces (" ") in the separator match zero or more whitespace characters.
        A separator consisting only of spaces must match at least one
        whitespace.
    endian : str, optional
        Endianess of the data in file, e.g. 'little' or 'big'. If endian is 
        specified and it is different than sys.endian, data is byteswapped. 
        By default no byteswapping is done.
    """  
    dtype = np.dtype(dtype)
    count = np.multiply.reduce(shape) * dtype.itemsize
    a = np.fromfile(file, dtype, count, sep)
    if endian == sys.byteorder:
        return a.reshape(shape)  
    elif endian not in ("little", "big"):
        raise ValueError("Endian should be either 'little' or 'big'")
    else:
        return a.reshape(shape).byteswap(True)
   
#def refind(n1 = 1, n3 = None, n2 = None):
#    """Returns material array (eps)."""
#    if n3 is None:
#        if n2 is None:
#            n3 = n1
#            n2 = n1
#        else:
#            raise ValueError("Both n2, and n3 must be set")
#    if n2 is None:
#        n2 = n1
#    return np.array([n1,n2,n3])


def _reorder(data, order, possible_order):
    """
    Helper function to reorder data based on a passed order and the possible order string

    Parameters
    ----------
    data : array

    order : str

    possible_order: str


    Returns
    ----------
    data : array
        A new array or same array (if no transposing and data copying was made)
    -------

    """
    # If not in <possible_order> order, then try to rearrange to correct order
    if order != possible_order:
        # If not in zxyn order, then we must transpose data
        try:
            axes = (order.find(c) for c in possible_order)
            axes = tuple((i for i in axes if i != -1))
            return np.transpose(data, axes)
        except:
            raise ValueError("Invalid value for 'order'. "
                             "Must be a permutation of '{}' characters".format(possible_order))
    else:
        return data


def _r3(shape):
    """
    Returns r vector array of given shape.
    Parameters
    ----------
    shape : (int, int, int)
        The size of the domain in z, y, and x.

    Returns
    -------
    return_value : tuple

    """
    # Create evenly spaced points across domain
    az, ay, ax = [np.arange(-length / 2. + .5, length / 2. + .5) for length in shape]
    # Create meshgrid
    zz, yy, xx = np.meshgrid(az, ay, ax, indexing="ij")

    return xx, yy, zz


def sphere_mask(shape, radius, offset=(0, 0, 0)):
    """
    Returns a bool mask array that defines a sphere.

    The resulting bool array will have ones (True) insede the sphere
    and zeros (False) outside of the sphere that is centered in the compute
    box center.

    Parameters
    ----------
    shape : (int, int, int)
        A tuple of (nlayers, height, width) defining the bounding box of the sphere.
    radius: float
        Radius of the sphere in pixels.
    offset: (int, int, int), optional
        Offset of the sphere from the center of the bounding box. The coordinates
        are (x,y,z).

    Returns
    -------
    out : array
        Bool array defining the sphere.
    """
    # 3D meshgrid result so that each component is defined over the whole domain
    xx, yy, zz = _r3(shape)
    # Calculate radius at each point
    r = ((xx - offset[0]) ** 2 + (yy - offset[1]) ** 2 + (zz - -offset[2]) ** 2) ** 0.5
    # Create a boolean mask. 1 inside sphere, 0 outside
    mask = (r <= radius)

    return mask


def nematic_droplet_director(shape, radius, profile="r", return_mask=False):
    """
    Returns nematic director data of a nematic droplet with a given radius.

    Parameters
    ----------
    shape : (int, int, int)
        (nz,nx,ny) shape of the output data box. First dimension is the
        number of layers, second and third are the x and y dimensions of the box.
    radius : float
        radius of the droplet.
    profile : str, optional
        Director profile type. It can be a radial profile "r", or homeotropic
        profile with director orientation specified with the parameter "x", "y",
        or "z", or as a director tuple e.g. (np.sin(0.2),0,np.cos(0.2)). Note that
        director length  defines order parameter (S=1 for this example).
    return_mask : bool, optional
        Whether to output mask data as well

    Returns
    -------
    out : array or tuple of arrays
        A director data array, or tuple of director mask and director data arrays.
    """
    # Size of the domain
    nz, ny, nx = shape
    # Preallocate output result
    out = np.zeros(shape=(nz, ny, nx, 3), dtype=FDTYPE)
    # 3D meshgrid result so that each component is defined over the whole domain
    xx, yy, zz = _r3(shape)

    # Calculate radius at each point
    r = (xx ** 2 + yy ** 2 + zz ** 2) ** 0.5
    # Logical mask for everything inside the droplet
    mask = (r <= radius)
    # Logical mask for inside the droplet, but not at the center
    m = np.logical_and(mask, r != 0.)
    # Radius values where mask is true
    rm = r[m]

    # Create director profile
    if profile == "r":
        # Radial anchoring
        out[..., 0][m] = xx[m] / rm
        out[..., 1][m] = yy[m] / rm
        out[..., 2][m] = zz[m] / rm
    elif isinstance(profile, str):
        # x, y, or z orientation
        index = {"x": 0, "y": 1, "z": 2}
        try:
            i = index[profile]
            out[..., i][m] = 1.
        except KeyError:
            raise ValueError("Unsupported profile type!")
    else:
        # Custom specified profile
        try:
            x, y, z = profile
            out[..., 0][m] = x
            out[..., 1][m] = y
            out[..., 2][m] = z
        except:
            raise ValueError("Unsupported profile type!")

    # Returns
    if return_mask:
        return mask, out
    else:
        return out


def cholesteric_director(shape, pitch, hand="left"):
    """
    Returns a cholesteric director data.
    
    Parameters
    ----------
    shape : (int, int, int)
        (nz,nx,ny) shape of the output data box. First dimension is the 
        number of layers, second and third are the x and y dimensions of the box.
    pitch : float
        Cholesteric pitch in pixel units.
    hand : str, optional
        Handedness of the pitch; either 'left' (default) or 'right'

    Returns
    -------
    out : ndarray
        A director data array
    """
    # Size of output data box
    nz, ny, nx = shape

    # Calculate rotational angle at each layer
    phi = 2*np.pi/pitch*np.arange(nz)

    # Change sign based on handedness of rotation
    if hand == 'left':
        pass
    elif hand == "right":
        phi *= -1
    else:
        raise ValueError("Unknown handedness '{}'".format(hand))

    # Create output a
    out = np.zeros(shape=(nz, ny, nx, 3), dtype=FDTYPE)

    # Fill output
    for i in range(nz):
        out[i, ..., 0] = np.cos(phi[i])
        out[i, ..., 1] = np.sin(phi[i])

    return out


def nematic_droplet_data(shape, radius, profile="r", no=1.5, ne=1.6, nhost=1.5):
    """
    Returns nematic droplet optical_data.

    This function returns a thickness,  material_eps, angles, info tuple
    of a nematic droplet, suitable for light propagation calculation tests.

    Parameters
    ----------
    shape : tuple[int]
        (nz,nx,ny) shape of the stack. First dimension is the number of layers,
        second and third are the x and y dimensions of the compute box.
    radius : float
        radius of the droplet.
    profile : str, optional
        Director profile type. It can be a radial profile "r", or homeotropic
        profile with director orientation specified with the parameter "x",
        "y", or "z".
    no : float, optional
        Ordinary refractive index of the material (1.5 by default)
    ne : float, optional
        Extraordinary refractive index (1.6 by default)
    nhost : float, optional
        Host material refractive index (1.5 by default)

    Returns
    -------
    out : tuple[np.ndarray]
        A (thickness, material_eps, angles) tuple of three arrays
    """
    # Create the director and droplet mask
    mask, director = nematic_droplet_director(shape, radius, profile=profile, return_mask=True)

    # Turns the director into optical data
    return director2data(director, mask=mask, no=no, ne=ne, nhost=nhost)


def cholesteric_droplet_data(shape, radius, pitch, hand="left", no=1.5, ne=1.6, nhost=1.5):
    """
    Returns cholesteric droplet optical_data.
    
    This function returns a thickness,  material_eps, angles, info tuple 
    of a cholesteric droplet, suitable for light propagation calculation tests.
    
    Parameters
    ----------
    shape : tuple[int]
        (nz, nx, ny) shape of the stack. First dimension is the number of layers,
        second and third are the x and y dimensions of the compute box.
    radius : float
        radius of the droplet.
    pitch : float
        Cholesteric pitch in pixel units.
    hand : str, optional
        Handedness of the pitch; either 'left' (default) or 'right'
    no : float, optional
        Ordinary refractive index of the material (1.5 by default)
    ne : float, optional
        Extraordinary refractive index (1.6 by default)
    nhost : float, optional
        Host material refractive index (1.5 by default)
        
    Returns
    -------
    out : tuple[np.ndarray]
        A (thickness, material_eps, angles) tuple of three arrays
    """
    # Calculate director
    director = cholesteric_director(shape, pitch, hand=hand)
    # Calculate spherical mask
    mask = sphere_mask(shape, radius)
    # Combine mask and directed to obtain final data, then return
    return director2data(director, mask=mask, no=no, ne=ne, nhost=nhost)


@numba.guvectorize([(NF32DTYPE[:], NF32DTYPE[:]), (NF64DTYPE[:], NFDTYPE[:])], "(n)->()", cache=NUMBA_CACHE)
def director2order(data, out):
    """
    Converts director data to scalar order parameter, S.
    The length of the director is assumed to be S.

    Parameters
    ----------
    data : array
        Director in cartesian (x, y, z) representation from which to extract scalar order parameter
    out : array
        Scalar order parameter calculated from the input director <data>

    Returns
    -------

    """

    # Check that vector is a 3-vector
    if data.shape[0] != 3:
        raise TypeError("invalid shape")

    # Split vector into x, y, and z components
    x = data[0]
    y = data[1]
    z = data[2]

    # Calculate the scalar order parameter, S
    s = np.sqrt(x**2 + y**2 + z**2)

    # Return
    out[0] = s


@numba.guvectorize([(NF32DTYPE[:], NF32DTYPE[:]), (NF64DTYPE[:], NFDTYPE[:])], "(n)->(n)", cache=NUMBA_CACHE)
def director2angles(data, out):
    """
    Converts director data (x, y, z) to angles (yaw, theta, phi).

    Parameters
    ----------
    data : array
        Cartesian representation of a 3-vector.
    out : array
        Angle representation of a 3-vector.

    Returns
    -------

    """

    # Ensure Shape is correct
    if data.shape[0] != 3:
        raise TypeError("Invalid shape")

    # Extract cartesian lengths
    x = data[0]
    y = data[1]
    z = data[2]

    # Calculate angles
    yaw = 0.
    phi = np.arctan2(y, x)
    theta = np.arctan2(np.sqrt(x ** 2 + y ** 2), z)

    # Store output
    out[0] = yaw
    out[1] = theta
    out[2] = phi


@numba.guvectorize([(NF32DTYPE[:], NF32DTYPE[:]), (NF64DTYPE[:], NFDTYPE[:])], "(n)->(n)", cache=NUMBA_CACHE)
def angles2director(data, out):
    """
    Converts angles data (yaw, theta, phi) to director in cartesian representation (x,y,z).

    This function does not take the scalar order parameter into account, it assumes a value of 1.

    Parameters
    ----------
    data : array
        Angle representation of a 3-vector.
    out : array
        Cartesian representation of a 3-vector.

    Returns
    -------

    """

    # Check that director is correct shape
    if data.shape[0] != 3:
        raise TypeError("invalid shape")

    # Scalar order parameter, S
    s = 1.
    # Separate angles
    theta = data[1]
    phi = data[2]

    # Calculate trigonometric values of angles
    cos_theta = np.cos(theta)
    sin_theta = np.sin(theta)
    cos_phi = np.cos(phi)
    sin_phi = np.sin(phi)

    # Calculate x component
    out[0] = s * cos_phi * sin_theta
    # Calculate y component
    out[1] = s * sin_phi * sin_theta
    # Calculate z component
    out[2] = s * cos_theta


def expand(data, shape, x_off=None, y_off=None, z_off=None, fill_value=0.):
    """
    Creates a new scalar or vector field data with an expanded volume.
    Missing data points are filled with fill_value. Output data shape
    must be larger than the original data.
    
    Parameters
    ----------
    data : array_like
       Input vector or scalar field data
    shape : array_like
       A scalar or length 3 vector that defines the volume of the output data
    x_off : int, optional
       Data offset value in the x direction. If provided, original data is 
       copied to new data starting at this offset value. If not provided, data 
       is copied symmetrically (default).
    y_off : int, optional
       Data offset value in the x direction. 
    z_off : int, optional
       Data offset value in the z direction.     
    fill_value : array_like
       A length 3 vector of default values for the border volume data points.
       
    Returns
    -------
    out : array_like
       Expanded output data
    """
    # Ensure data is numpy array
    data = np.asarray(data)
    # size of data in z, x, and y dimension
    # TODO: This seems confusing for the user. Standard order is "zyxn", not "zxyn" for director.
    nz, nx, ny = shape

    if nz >= data.shape[0] and ny >= data.shape[1] and nx >= data.shape[2]:
        # Preallocate output
        out = np.empty(shape=shape + data.shape[3:], dtype=data.dtype)
        # Fill in with default value
        out[..., :] = fill_value

        # Set default values for any offset values not provided
        if x_off is None:
            x_off = (shape[1] - data.shape[1]) // 2
        if y_off is None:
            y_off = (shape[2] - data.shape[2]) // 2
        if z_off is None:
            z_off = (shape[0] - data.shape[0]) // 2

        out[z_off:data.shape[0] + z_off, y_off:data.shape[1] + y_off, x_off:data.shape[2] + x_off, ...] = data
        return out 
    else:
        raise ValueError("Requested shape {} is not larger than original data's shape".format(shape))


_REFIND_DECL = [(NF32DTYPE[:], NF32DTYPE[:]),
                (NF64DTYPE[:], NFDTYPE[:]),
                (NC64DTYPE[:], NC64DTYPE[:]),
                (NC128DTYPE[:], NCDTYPE[:])]


@numba.njit(_REFIND_DECL, cache=NUMBA_CACHE)
def _refind2eps(refind, out):
    """
    Helper function for refind2eps() in order to work in parallel.

    Parameters
    ----------
    refind : array_like
        complex refractive indices
    out : array_like
        dielectric tensor elements

    """
    # Convert from index of refraction value to dielectric value
    out[0] = refind[0]**2
    out[1] = refind[1]**2
    out[2] = refind[2]**2


@numba.guvectorize(_REFIND_DECL, "(n)->(n)", cache=NUMBA_CACHE)
def refind2eps(refind, out):
    """
    Converts three eigen (complex) refractive indices to three eigen dielectric tensor elements

    Parameters
    ----------
    refind : array_like
        complex refractive indices
    out : array_like
        dielectric tensor elements
    """

    assert refind.shape[0] == 3

    _refind2eps(refind, out)


_EPS_DECL = ["(float32,float32[:],float32[:])", "(float64,float64[:],float64[:])",
             "(float32,complex64[:],complex64[:])", "(float64,complex128[:],complex128[:])"]


@numba.njit(_EPS_DECL, cache=NUMBA_CACHE)
def _uniaxial_order(order, eps, out):
    # Isotropic dielectric constant
    m = (eps[0] + eps[1] + eps[2]) / 3.
    # Dielectric constant anisotropy
    delta = eps[2] - (eps[0] + eps[1]) / 2.
    # Check order
    if order == 0.:
        # Isotropic case
        eps1 = m
        eps3 = m
    else:
        # Uniaxial
        eps1 = m - 1. / 3. * order * delta
        eps3 = m + 2. / 3. * order * delta

    out[0] = eps1
    out[1] = eps1
    out[2] = eps3

    return out


_EPS_DECL_VEC = ["(float32[:],float32[:],float32[:])","(float64[:],float64[:],float64[:])",
             "(float32[:],complex64[:],complex64[:])","(float64[:],complex128[:],complex128[:])"]


@numba.guvectorize(_EPS_DECL_VEC ,"(),(n)->(n)", cache = NUMBA_CACHE)
def uniaxial_order(order, eps, out):
    """
    uniaxial_order(order, eps)
    
    Calculates uniaxial dielectric tensor of a material with a given orientational order parameter
    from a diagonal dielectric (eps) tensor of the same material with perfect order (order = 1)
    
    >>> uniaxial_order(0,[1,2,3.])
    array([ 2.+0.j,  2.+0.j,  2.+0.j])
    >>> uniaxial_order(1,[1,2,3.])
    array([ 1.5+0.j,  1.5+0.j,  3.0+0.j])
    """
    assert eps.shape[0] == 3
    _uniaxial_order(order[0], eps, out)

# length 4 magic number for file ID
MAGIC = b"dtms"
VERSION = b"\x00"

"""
IOs functions
-------------
"""


def save_stack(file, optical_data):
    """Saves optical data to a binary file in ``.dtms`` format.
    
    Parameters
    ----------
    file : file, str
        File or filename to which the data is saved.  If file is a file-object,
        then the filename is unchanged.  If file is a string, a ``.dtms``
        extension will be appended to the file name if it does not already
        have one.
    optical_data: optical data tuple
        A valid optical data
    """    
    own_fid = False
    d,epsv,epsa = validate_optical_data(optical_data)
    try:
        if isinstance(file, str):
            if not file.endswith('.dtms'):
                file = file + '.dtms'
            f = open(file, "wb")
            own_fid = True
        else:
            f = file
        f.write(MAGIC)
        f.write(VERSION)
        np.save(f,d)
        np.save(f,epsv)
        np.save(f,epsa)
    finally:
        if own_fid == True:
            f.close()


def load_stack(file):
    """Load optical data from file.
    
    Parameters
    ----------
    file : file, str
        The file to read.
    """
    own_fid = False
    try:
        if isinstance(file, str):
            f = open(file, "rb")
            own_fid = True
        else:
            f = file
        magic = f.read(len(MAGIC))
        if magic == MAGIC:
            if f.read(1) != VERSION:
                raise OSError("This file was created with a more recent version of dtmm. Please upgrade your dtmm package!")
            d = np.load(f)
            epsv = np.load(f)
            epsa = np.load(f)
            return d, epsv, epsa
        else:
            raise OSError("Failed to interpret file {}".format(file))
    finally:
        if own_fid == True:
            f.close()

#@numba.guvectorize(["(complex64[:],float32[:],complex64[:])","(complex128[:],float64[:],complex128[:])"],"(n),()->(n)")
#def eps2ueps(eps, order, out):
#    """
#    eps2ueps(eps, order)
#    
#    Calculates uniaxial dielectric tensor of a material with a given orientational order parameter
#    from a diagonal dielectric (eps) tensor of the same material with perfect order (order = 1)
#    
#    >>> eps2ueps([1,2,3.],0)
#    array([ 2.+0.j,  2.+0.j,  2.+0.j])
#    >>> eps2ueps([1,2,3.],1)
#    array([ 1.5+0.j,  1.5+0.j,  3.0+0.j])
#    """
#    assert eps.shape[0] == 3
#    _uniaxial_order(order[0], eps, out)
#    
#@numba.guvectorize(["(complex64[:],complex64[:])","(complex128[:],complex128[:])"],"(n)->(n)")
#def eps2ieps(eps, out):
#    """
#    eps2ieps(eps)
#    
#    Calculates isotropic dielectric tensor of a material with a given orientational order parameter order=0
#    from a diagonal dielectric (eps) tensor of the same material with perfect order (order = 1)
#
#    """
#    assert eps.shape[0] == 3
#    _uniaxial_order(0., eps, out)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
