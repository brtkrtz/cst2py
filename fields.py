"""
Import CST field results.


Read field results from the "2D/3D Results"-Folder in CST.

This code uses the "Result Reader DLL". From 2019 on, it is not documented in the CST help any more, but still provided. One is supposed to use the export methods of CST instead, but still allowed to ask the support.

Last Help-File: 
C:/Program Files (x86)/CST STUDIO SUITE 2018/Online Help/advanced/resultreadingdll.htm

2019 03 29 Bernd Breitkreutz
"""


import os
import shutil
import ctypes
import _ctypes # freelibrary, to reuse dll for different projects
import winreg
import sys
import platform
import h5py
import numpy
import re
import time
import datetime

def _get_CST_InstallPath(CST_version):
    wr_handle = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
    rkey = winreg.OpenKey(wr_handle, "SOFTWARE\\Wow6432Node\\CST AG\\CST DESIGN ENVIRONMENT\\"+str(CST_version))
    sUniCode = winreg.QueryValueEx(rkey, "INSTALLPATH")[0]
    return sUniCode


def _get_CST_result_reader_path(CST_version, verbose=False):
    install_path = _get_CST_InstallPath(CST_version)
    if verbose: print("CST install path:  %s" % install_path)
    bitness, os_name = platform.architecture()
    if verbose: print("OS name:  %s, OS bitness: %s" % os_name, bitness)
    if bitness.startswith("64"):
        install_path = os.path.join(install_path,  u"AMD64")
        dll_name = u"CSTResultReader_AMD64.dll"
    else:
        dll_name = u"CSTResultReader.dll"
    os.chdir(install_path) # We need to change to the DLL path to find other required DLLs
    if verbose: print("Changed dir to %s" % os.getcwd())
    return os.path.join(install_path, dll_name)


def _load_CST_result_reader_dll(CST_version, verbose=False):
    dll_path = _get_CST_result_reader_path(CST_version)
    if verbose: print("Trying to load dll from", dll_path)
    if not os.path.exists(dll_path):
        sys.exit("Could not find ResultReader dll at "+dll_path)
    cstlib = ctypes.WinDLL(dll_path)
    iVersion = ctypes.c_int()
    cstlib.CST_GetDLLVersion(ctypes.byref(iVersion))
    if verbose: print("DLL version:", iVersion)
    return cstlib


def _get_item_names(pHandle, cstlib, search_string):
    ERROR_CODE_MEMORY = 8
    buf_size = 10000
    discovered_str = ""
    num_results = ctypes.c_int(-1)
    while True:
        discovered_str = ctypes.create_string_buffer(buf_size)
        ret = cstlib.CST_GetItemNames(ctypes.byref(pHandle), ctypes.c_char_p(search_string.encode('utf-8')), \
                                      discovered_str, ctypes.c_int(buf_size), ctypes.pointer(num_results))
        if ret==0:
            break
        elif ret==ERROR_CODE_MEMORY:
            buf_size *= 2
            discovered_str = ctypes.create_string_buffer(buf_size)
        else:
            sys.exit("Error reading items: "+str(ret))
    item_list = discovered_str.value.split(b"\n")
    return item_list


def _check_array(Matrix, dExpectedSum, sName):
    dSum = 0
    for x in Matrix:
        dSum += x
    bOK = abs(dSum/dExpectedSum-1)<0.001
    if not bOK:
        print("Error: Something might be wrong with reading ", sName)
    return bOK


def load_fields(CST_version, sProjectPath, sProjectName, freqScale, verbose=False):
    """
    Load all 3D Fields of a project
    """
    # Load DLL, get DLL version
    cstlib = _load_CST_result_reader_dll(CST_version)
    # Open project
    pHandle = ctypes.c_void_p()
    print("Open Project:", os.path.join(sProjectPath, sProjectName))
    ret = cstlib.CST_OpenProject(os.path.join(sProjectPath, sProjectName).encode('utf-8'), ctypes.byref(pHandle))#
    print(pHandle)    
    if ret!=0: sys.exit("Open Project Error: "+str(ret))
    # Get all project items
    efield_names = _get_item_names(pHandle, cstlib, "E-Field")
    if len(efield_names[0]) == 0: efield_names=[]
    print("---------------------")
    print("All E-Fields in project are:")
    for nam in efield_names: print(nam)
    print("---------------------")
    hfield_names = _get_item_names(pHandle, cstlib, "H-Field")
    if len(hfield_names[0]) == 0: hfield_names=[]
    print("---------------------")
    print("All H-Fields in project are:")
    for nam in hfield_names: print(nam)
    print("---------------------")
    # Get mesh dimensions
    t_array = ctypes.c_int * 3
    Nxyz = t_array(0,0,0)
    ret = cstlib.CST_GetHexMeshInfo(ctypes.byref(pHandle), ctypes.byref(Nxyz))
    print("nx/ny/nz =", Nxyz[0], Nxyz[1], Nxyz[2])
    Np = Nxyz[0]*Nxyz[1]*Nxyz[2]
    # Read mesh lines
    t_xyzlines_array = ctypes.c_double * (Nxyz[0]+Nxyz[1]+Nxyz[2])
    xyzlines = t_xyzlines_array()
    ret = cstlib.CST_GetHexMesh(ctypes.byref(pHandle), ctypes.byref(xyzlines))
    # Ergebnis: mesh-lines
    xlines = numpy.array(xyzlines[0:Nxyz[0]])
    ylines = numpy.array(xyzlines[Nxyz[0]:Nxyz[0]+Nxyz[1]])
    zlines = numpy.array(xyzlines[Nxyz[0]+Nxyz[1]:Nxyz[0]+Nxyz[1]+Nxyz[2]])
    #############
    # Read results
    n = len(efield_names + hfield_names)
    fields3d = [0]*n
    field_names = [0]*n
    freq_names = [0]*n
    freqs = [0]*n
    for i, sTreePath in enumerate(efield_names + hfield_names):
        # example:
        # sTreePath = b'2D/3D Results\H-Field\h-field (f=8) [1]'
        iResultNumber = 0
        resSize = ctypes.c_int(-1)
        ret = cstlib.CST_Get3DHexResultSize(ctypes.byref(pHandle), sTreePath, iResultNumber, ctypes.byref(resSize))
        if verbose: print("\n\nRead ", resSize, " floats from ",sTreePath, end=' ')
        field3d = (ctypes.c_float * (resSize.value))()
        ret = cstlib.CST_Get3DHexResult(ctypes.byref(pHandle), sTreePath, iResultNumber, ctypes.byref(field3d))
        # 3D-Felder
        field3d = numpy.array(field3d[0::2]) + 1j*numpy.array(field3d[1::2])
        x_comp_3d = (field3d[0*Np : 1*Np]).reshape((len(zlines), len(ylines), len(xlines)))
        x_comp_3d=numpy.swapaxes(x_comp_3d, 0, 2)
        y_comp_3d = (field3d[1*Np : 2*Np]).reshape((len(zlines), len(ylines), len(xlines)))
        y_comp_3d=numpy.swapaxes(y_comp_3d, 0, 2)
        z_comp_3d = (field3d[2*Np : 3*Np]).reshape((len(zlines), len(ylines), len(xlines)))
        z_comp_3d=numpy.swapaxes(z_comp_3d, 0, 2)
        fields3d[i] = [x_comp_3d, y_comp_3d, z_comp_3d]
        # Feldname, Frequenz
        p=re.compile('[H,E]-Field')    
        field_names[i] = p.findall(str(sTreePath))[0]
        p=re.compile(r'\(f=[-+]?\d+\.?\d*\)')
        freq_name = p.findall(str(sTreePath))[0]
        freq_names[i] = freq_name
        freqs[i] = float(freq_name[3:-1]) * freqScale
    # Close project
    ret = cstlib.CST_CloseProject(ctypes.byref(pHandle))#
    if ret!=0: sys.exit("Close Project Error: "+str(ret))
    _ctypes.FreeLibrary(cstlib._handle)
    return efield_names, hfield_names, xlines, ylines, zlines, fields3d, field_names, freq_names, freqs


def slice_1d(efield_names, hfield_names, xlines, ylines, zlines, fields3d, x0, y0):  
    Np = len(xlines)*len(ylines)*len(zlines)
    # x0, y0 in xlines, ylines nachschlagen -> ix, iy
    ix = (numpy.abs(xlines-x0)).argmin()
    x0 = xlines[ix]
    dx = xlines[ix+1]-xlines[ix]
    iy = (numpy.abs(ylines-y0)).argmin()
    y0 = ylines[iy]
    dy = ylines[iy+1]-ylines[iy]

    n = len(efield_names + hfield_names)
    z_comps = [0]*n
    x_grads = [0]*n
    y_grads = [0]*n
    for i, sTreePath in enumerate(efield_names + hfield_names):
        field3d = fields3d[i]

        # zComp vorbereiten
        z_comp_3d = field3d[2]
        z_comp_0 = z_comp_3d[ix, iy, :]
        z_comp_x = z_comp_3d[ix+1, iy, :]
        z_comp_y = z_comp_3d[ix, iy+1, :]

        # Ergebnis: 1D-slice
        z_comps[i] = z_comp_0
        x_grads[i] = (z_comp_x-z_comp_0) / dx
        y_grads[i] = (z_comp_y-z_comp_0) / dy
    return z_comps, x_grads, y_grads, x0, y0


def save_hd5_3d(hd5path, efield_names, hfield_names, xlines, ylines, zlines, fields3d, field_names, freq_names, freqs): 
    for i, sTreePath in enumerate(efield_names + hfield_names):
        with h5py.File(os.path.join(hd5path, field_names[i]+' '+freq_names[i]+'.hdf5'),'w') as f:
            print(f)
            f.create_dataset('Type', data=field_names[i])
            f.create_dataset('f', data=freqs[i])
            f.create_dataset('x', data=xlines)
            f.create_dataset('y', data=ylines)
            f.create_dataset('z', data=zlines)
            f.create_dataset('field3d', data=fields3d[i])


def save_hd5_1d(hd5path, efield_names, hfield_names, zlines, z_comps, x_grads, y_grads, field_names, freq_names, freqs, x0, y0):  
    for i, sTreePath in enumerate(efield_names + hfield_names):#f"{(x0/1e-3):.3f}".rstrip('0').rstrip('.')    str(y0/1e-3)
        with h5py.File(os.path.join(hd5path, field_names[i]+' '+freq_names[i]+' x0='+f"{(x0/1e-3):.3f}".rstrip('0').rstrip('.')+' y0='+f"{(y0/1e-3):.3f}".rstrip('0').rstrip('.')+'.hdf5'),'w') as f:
            print(f)
            f.create_dataset('Type', data=field_names[i])
            f.create_dataset('f', data=freqs[i])
            f.create_dataset('x0', data=x0)
            f.create_dataset('y0', data=y0)
            f.create_dataset('z', data=zlines)
            f.create_dataset('zComp', data=z_comps[i])
            f.create_dataset('xGrad', data=x_grads[i])
            f.create_dataset('yGrad', data=y_grads[i])


def project_to_3d_files(sProjectPath, sProjectName, hd5BasePath, freqScale, CST_version=2019, force_overwrite=False):
    if not os.path.exists(hd5BasePath):
        os.mkdir(hd5BasePath)

    hd5path = os.path.join(hd5BasePath, sProjectName[:-4])
    if not os.path.exists(hd5path):
        os.mkdir(hd5path)
    else:
        if os.listdir(hd5path):  # returns True if there are files in the directory
            if force_overwrite:
                shutil.rmtree(hd5path)
                os.mkdir(hd5path)
            else:
                # print('hd5-files already exist for project ' + sProjectName + ' -> Skipping')
                return 1

    efield_names, hfield_names, xlines, ylines, zlines, fields3d, field_names, freq_names, freqs = \
                        load_fields(CST_version, sProjectPath, sProjectName, freqScale)
    save_hd5_3d(hd5path, efield_names, hfield_names, xlines, ylines, zlines, fields3d, field_names, freq_names, freqs)
    return 0


def all_projects_to_3d_files(sProjectPath, freqScale, hd5_folder='hd5', CST_version=2019, force_overwrite=False):
    project_names = []
    for file in os.listdir(sProjectPath):
        if file.endswith(".cst"):
            project_names.append(file)
    print('\n\n\n3D export. Found projects:', project_names)

    hd5BasePath = os.path.join(sProjectPath[:-1], hd5_folder)
    if not os.path.exists(hd5BasePath):
        os.mkdir(hd5BasePath)

    for sProjectName in project_names:
        print("\n\n\n\n")
        print("#####################################")
        print("####", sProjectName)
        print("#####################################")
        t = time.time()
        retval = project_to_3d_files(sProjectPath, sProjectName, hd5BasePath, freqScale, CST_version, force_overwrite)
        if retval ==1:
            print('hd5-files already exist!')
        elapsed = numpy.round(time.time() - t)
        print('elapsed time: '+str(elapsed))


def project_to_1d_files(sProjectPath, sProjectName, hd5BasePath, x0, y0, freqScale, CST_version=2019, force_overwrite=False):
    if not os.path.exists(hd5BasePath):
        os.mkdir(hd5BasePath)

    hd5path = os.path.join(hd5BasePath, sProjectName[:-4])
    if not os.path.exists(hd5path):
        os.mkdir(hd5path)
    else:
        if os.listdir(hd5path):  # returns True if there are files in the directory
            if force_overwrite:
                shutil.rmtree(hd5path)
                os.mkdir(hd5path)
            else:
                # print('hd5-files already exist for project ' + sProjectName + ' -> Skipping')
                return 1

    efield_names, hfield_names, xlines, ylines, zlines, fields3d, field_names, freq_names, freqs = \
                        load_fields(CST_version, sProjectPath, sProjectName, freqScale)
    z_comps, x_grads, y_grads, x0, y0 = slice_1d(efield_names, hfield_names, xlines, ylines, zlines, fields3d, x0, y0)
    save_hd5_1d(hd5path, efield_names, hfield_names, zlines, z_comps, x_grads, y_grads, field_names, freq_names, freqs, x0, y0)
    return 0


def all_projects_to_1d_files(sProjectPath, x0, y0, freqScale, hd5_folder='hd5', CST_version=2019, force_overwrite=False):
    project_names = []
    for file in os.listdir(sProjectPath):
        if file.endswith(".cst"):
            project_names.append(file)
    print('\n\n\n1D export. Found projects:', project_names)

    hd5BasePath = os.path.join(sProjectPath[:-1], hd5_folder)
    if not os.path.exists(hd5BasePath):
        os.mkdir(hd5BasePath)

    for sProjectName in project_names:
        print("\n\n\n\n")
        print("#####################################")
        print("####", sProjectName)
        print("#####################################")
        t = time.time()
        retval = project_to_1d_files(sProjectPath, sProjectName, hd5BasePath, x0, y0, freqScale, CST_version, force_overwrite)
        if retval ==1:
            print('hd5-files already exist!')
        elapsed = numpy.round(time.time() - t)
        print('elapsed time: '+str(elapsed))


if __name__ == "__main__":
    CST_version = 2019
    sProjectPath = os.path.abspath('.') + r"\\cstdemo\\"
    freqScale = 1e9
    x0 = 0
    y0 = 0
    all_projects_to_1d_files(sProjectPath, x0, y0, freqScale, 'hd5', CST_version, force_overwrite=True)
    all_projects_to_3d_files(sProjectPath, freqScale, 'hd5_3d', CST_version, force_overwrite=True)

