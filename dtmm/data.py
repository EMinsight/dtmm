# -*- coding: utf-8 -*-
"""
Created on Tue Oct 10 09:44:09 2017

@author: andrej
"""

from __future__ import absolute_import, print_function, division

import numpy as np
#from mayavi import mlab

#from dir_to_stack import dirtostack

import numba
import sys

from dtmm.conf import  NF32DTYPE, F32DTYPE, FDTYPE,NF64DTYPE, F64DTYPE, NUMBA_CACHE


def read_director(file, shape, dtype = "float32",  sep = "", endian = sys.byteorder, order = "zyxn", nvec = "xyz"):
    """Reads raw director data from a binary file. 
    
    A convinient way to read director data from file. 
    
    Parameters
    ----------
    file : str or file
        Open file object or filename.
    shape : sequence of ints
        Shape of the data array, e.g., ``(50, 24, 34, 3)``
    dtype : data-type
        Data type of the raw data. It is used to determine the size of the items 
        in the file.
    endian : str, optional
        Endianess of the data in file, e.g. 'little' or 'big'. If endian is 
        specified and it is different than sys.endian, data is byteswapped. 
        By default no byteswapping is done. 
    nvec : str, optional
        Order of the director data coordinates. Any permutation of 'x', 'y' and 
        'z', e.g. 'yxz', 'zxy' ... 
    """
    try:
        i,j,k,c = shape
    except:
        raise TypeError("shape must be director data shape (z,x,y,n)")
    data = read_raw(file, shape, dtype, sep = sep, endian = endian)
    return raw2director(data, order, nvec)

def director2data(director, mask = None, no = 1.5, ne = 1.6, nhost = None, thickness = None):
    """Builds optical data from director data"""
    material = np.empty(shape = director.shape, dtype = F32DTYPE)
    if mask is None:
        material[...] = refind2eps([no,no,ne])[None,...] 
        material = uniaxial_order(director2order(director), material, out = material)
    else:
        material[mask,:] =  refind2eps([no,no,ne])[None,...] 
        material[np.logical_not(mask),:] = refind2eps([nhost,nhost,nhost])[None,...] 
        
    if thickness is None:
        thickness =np.ones(shape = (material.shape[0],))
    return  thickness, material, director2angles(director)

        
def validate_optical_data(data, homogeneous = False):
    """Validates optical data.
    
    This function inspects validity of the optical data, and makes proper data
    conversions to match the optical data format. In case data is not valid and 
    it cannot be converted to a valid data it raises an exception (ValueError). 
    
    Parameters
    ----------
    data : tuple of optical data
        A valid optical data tuple.
    homogeneous : bool, optional
        Whether data is for a homogenous layer. (Inhomogeneous by defult)
    
    Returns
    -------
    data : tuple
        Validated optical data tuple. 
    """
    thickness, material, angles = data
    thickness = np.asarray(thickness, dtype = "float32")
    if thickness.ndim == 0:
        thickness = thickness[None] #make it 1D
    elif thickness.ndim != 1:
        raise ValueError("Thickess dimension should be 1.")
    n = len(thickness)
    material = np.asarray(material)
    if np.issubdtype(material.dtype, np.complexfloating):
        material = np.asarray(material, dtype = "complex64")
    else:
        material = np.asarray(material, dtype = "float32")
    if (material.ndim == 1 and homogeneous) or (material.ndim==3 and not homogeneous):
        material = np.broadcast_to(material, (n,)+material.shape)# np.asarray([material for i in range(n)], dtype = material.dtype)
    if len(material) != n:
        raise ValueError("Material length should match thickness length")
    if (material.ndim != 2 and homogeneous) or (material.ndim != 4 and not homogeneous):
        raise ValueError("Invalid dimensions of the material.")
    angles = np.asarray(angles, dtype = "float32")
    if (angles.ndim == 1 and homogeneous) or (angles.ndim==3 and not homogeneous):
        angles = np.broadcast_to(angles, (n,)+angles.shape)
        #angles = np.asarray([angles for i in range(n)], dtype = angles.dtype)
    if len(angles) != n:
        raise ValueError("Angles length should match thickness length")
    if (angles.ndim != 2 and homogeneous) or (angles.ndim!=4 and not homogeneous):
        raise ValueError("Invalid dimensions of the angles.")

    if material.shape != angles.shape:
        raise ValueError("Incompatible shapes for angles and material")
 
    return thickness, material, angles

    
def raw2director(data, order = "zyxn", nvec = "xyz"):
    """Converts raw data to director array.
    
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
        A new array or same array (if no trasposing and data copying was made)
        
    Example
    -------
    
    >>> a = np.random.randn(10,11,12,3)
    >>> director = raw2director(a, "xyzn")
    """
    if order != "zyxn":
        #if not in zxyn order, then we must transpose data
        try:
            axes = (order.find(c) for c in "zyxn")
            axes = tuple((i for i in axes if i != -1))
            data = np.transpose(data, axes)
        except:
            raise ValueError("Invalid value for 'order'. Must be a permutation of 'xyzn' characters")
        
    if nvec != "xyz":
        index = {"x" : 0, "y": 1, "z" : 2}
        out = np.empty_like(data)
        for i,idn in enumerate(nvec):
            j = index.pop(idn)
            out[...,j] = data[...,i]
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
   
def refind(n1 = 1, n3 = None, n2 = None):
    """Returns material array (eps)."""
    if n3 is None:
        if n2 is None:
            n3 = n1
            n2 = n1
        else:
            raise ValueError("Both n2, and n3 must be set")
    if n2 is None:
        n2 = n1
    return np.array([n1,n2,n3])
    
def _r3(shape):
    """Returns r vector array of given shape."""
    nz,ny,nx = [l//2 for l in shape]
    az, ay, ax = [np.arange(-l / 2. + .5, l / 2. + .5) for l in shape]
    zz,yy,xx = np.meshgrid(az,ay,ax, indexing = "ij")
    return xx, yy, zz
    #r = ((xx/(nx*scale))**2 + (yy/(ny*scale))**2 + (zz/(nz*scale))**2) ** 0.5 
    #return r
    
    
def sphere_mask(shape, radius, offset = (0,0,0)):
    """Returns a bool mask array that defines a sphere.
    
    The resulting bool array will have ones (True) insede the sphere
    and zeros (False) outside of the sphere that is centered in the compute
    box center.
    
    Parameters
    ----------
    shape : (int,int,int)
        A tuple of (nlayers, height, width) defining the bounding box of the sphere.
    radius: int
        Radius of the sphere in pixels.
    offset: (int, int, int), optional
        Offset of the sphere from the center of the bounding box. The coordinates
        are (x,y,z).
        
    Returns
    -------
    out : array
        Bool array defining the sphere.
    """
    xx, yy, zz = _r3(shape)
    r = ((xx-offset[0])**2 + (yy-offset[1])**2 + (zz--offset[2])**2) ** 0.5 
    mask = (r <= radius)
    return mask    
    
def nematic_droplet_director(shape, radius, profile = "r", retmask = False):
    """Returns nematic director data of a nematic droplet with a given radius.
    
    Parameters
    ----------
    shape : tuple
        (nz,nx,ny) shape of the output data box. First dimension is the 
        number of layers, second and third are the x and y dimensions of the box.
    radius : float
        radius of the droplet.
    profile : str, optional
        Director profile type. It can be a radial profile "r", or homeotropic 
        profile with director orientation specified with the parameter "x", "y",
        or "z".
    retmask : bool, optional
        Whether to output mask data as well
        
    Returns
    -------
    out : array or tuple of arrays 
        A director data array, or tuple of director mask and director data arrays.
    """
    
    nz, ny, nx = shape
    out = np.zeros(shape = (nz,ny,nx,3), dtype = F32DTYPE)
    xx, yy, zz = _r3(shape)
    
    r = (xx**2 + yy**2 + zz**2) ** 0.5 
    mask = (r <= radius)
    m = np.logical_and(mask,r != 0.)
    rm = r[m]
    if profile == "r":
        out[...,0][m] = xx[m]/rm
        out[...,1][m] = yy[m]/rm
        out[...,2][m] = zz[m]/rm
    else:
        index = {"x": 0,"y": 1,"z": 2}
        try:
            i = index[profile]
            out[...,i][m] = 1.
        except KeyError:
            raise ValueError("Unsupported profile type!")
    if retmask == True:
        return mask, out
    else: 
        return out

#def nematic_droplet_data_old(shape, radius, profile = "r", 
#                         no = 1.5, ne = 1.6, nhost = 1.5):
#
#    mask, director = nematic_droplet_director(shape, radius, profile = profile, retmask = True)
#    material = refind2eps([refind(nhost), refind(no,ne)])
#    return np.ones(shape = (shape[0],)), mask, material, director2stack(director)

def nematic_droplet_data(shape, radius, profile = "r", no = 1.5, ne = 1.6, nhost = 1.5):
    """Returns nematic droplet optical_data.
    
    This function returns a thickness,  material_eps, angles, info tuple 
    of a nematic droplet, suitable for light propagation calculation tests.
    
    Parameters
    ----------
    shape : tuple
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
    out : tuple of length 3
        A (thickness, material_eps, angles) tuple of three arrays
    """
    mask, director = nematic_droplet_director(shape, radius, profile = profile, retmask = True)
    return director2data(director, mask = mask, no = no, ne = ne, nhost = nhost)
    
#    material = np.empty(shape = shape + (3,), dtype = F32DTYPE)
#    material[mask0,:] =  refind2eps([no,no,ne])[None,...] 
#    material[np.logical_not(mask0),:] = refind2eps([nhost,nhost,nhost])[None,...] 
#    return np.ones(shape = (shape[0],)), material, director2stack(director)
#

#    
#@numba.njit([NF32DTYPE[:,:,:,:](NF32DTYPE[:,:,:,:])])
#def director2stack(data):
#    """Converts director data (nx,ny,nz) to stack data (order,theta phi).
#    Director data should be a vector with size 0 <= order <= 1."""
#    nz,nx,ny,c = data.shape
#    out = np.empty(shape = (nz,nx,ny,3),dtype = F32DTYPE)
#
#    if c != 3:
#        raise TypeError("invalid shape")
#    for i in range(nz):
#        for j in range(ny):
#            for k in range(nx):
#                vec = data[i,j,k]
#                x = vec[0]
#                y = vec[1]
#                z = vec[2]
#                phi = np.arctan2(y,x)
#                theta = np.arctan2(np.sqrt(x**2+y**2),z)
#                tmp = out[i,j,k]
#                #id = tmp.view(UDTYPE)
#                
#                #id[0] = 0
#                tmp[0] = np.sqrt(x**2+y**2+z**2)
#                tmp[1] = theta
#                tmp[2] = phi
#    return out

@numba.guvectorize([(NF32DTYPE[:],NF32DTYPE[:]),(NF64DTYPE[:],NF64DTYPE[:])], "(n)->()", cache = NUMBA_CACHE)
def director2order(data, out):
    """Converts director data to order parameter (length of the director)"""
    c = data.shape[0]
    if c != 3:
        raise TypeError("invalid shape")
    x = data[0]
    y = data[1]
    z = data[2]
    s = np.sqrt(x**2+y**2+z**2)
    out[0] = s


@numba.guvectorize([(NF32DTYPE[:],NF32DTYPE[:]),(NF64DTYPE[:],NF64DTYPE[:])], "(n)->(n)", cache = NUMBA_CACHE)
def director2stack(data, out):
    """Converts director data to angles (yaw, theta phi)"""
    c = data.shape[0]
    if c != 3:
        raise TypeError("invalid shape")

    x = data[0]
    y = data[1]
    z = data[2]
    phi = np.arctan2(y,x)
    theta = np.arctan2(np.sqrt(x**2+y**2),z)
    #s = np.sqrt(x**2+y**2+z**2)
    out[0] = 0. #yaw = 0.
    out[1] = theta
    out[2] = phi


director2angles = director2stack

@numba.guvectorize([(NF32DTYPE[:],NF32DTYPE[:]),(NF64DTYPE[:],NF64DTYPE[:])], "(n)->(n)", cache = NUMBA_CACHE)
def angles2director(data, out):
    """Converts angles data (yaw,theta,phi) to director (nx,ny,nz)"""
    c = data.shape[0]
    if c != 3:
        raise TypeError("invalid shape")

    s = 1.
    theta = data[1]
    phi = data[2]

    ct = np.cos(theta)
    st = np.sin(theta)
    cf = np.cos(phi)
    sf = np.sin(phi)
    out[0] = s*cf*st
    out[1] = s*sf*st
    out[2] = s*ct

def add_isotropic_border(data, shape, xoff = None, yoff = None, zoff = None):
    """Adds isotropic border area to director or stack data"""
    nz,nx,ny = shape
    out = np.zeros(shape = shape + data.shape[3:], dtype = data.dtype)
    if xoff is None:
        xoff = (shape[1] - data.shape[1])//2
    if yoff is None:
        yoff = (shape[2] - data.shape[2])//2
    if zoff is None:
        zoff = (shape[0] - data.shape[0])//2

    out[:,xoff:data.shape[1]+xoff,yoff:data.shape[2]+yoff,:] = data
    return out 

_REFIND_DECL = ["(float32[:],float32[:])","(float64[:],float64[:])","(complex64[:],complex64[:])","(complex128[:],complex128[:])"]

@numba.njit(_REFIND_DECL, cache = NUMBA_CACHE)  
def _refind2eps(refind, out):
    out[0] = refind[0]**2
    out[1] = refind[1]**2
    out[2] = refind[2]**2

@numba.guvectorize(_REFIND_DECL,"(n)->(n)", cache = NUMBA_CACHE)  
def refind2eps(refind, out):
    """Converts three eigen (complex) refractive indices to three eigen dielectric tensor elements"""
    assert refind.shape[0] == 3
    _refind2eps(refind, out)
   
    
_EPS_DECL = ["(float32,float32[:],float32[:])","(float64,float64[:],float64[:])",
             "(float32,complex64[:],complex64[:])","(float64,complex128[:],complex128[:])"]
@numba.njit(_EPS_DECL, cache = NUMBA_CACHE)
def _uniaxial_order(order, eps, out):
    m = (eps[0] + eps[1] + eps[2])/3.
    delta = eps[2] - (eps[0] + eps[1])/2.
    if order == 0.:
        eps1 = m
        eps3 = m
    else:
        eps1 = m - 1./3. *order * delta
        eps3 = m + 2./3. * order * delta

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