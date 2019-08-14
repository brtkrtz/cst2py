# -*- coding: utf-8 -*-
"""Collection of functions to calculate stochastic cooling 

- Calculate Kicker constant, shunt impedance etc. from electric field.
- Convert beam parameters.
"""

import os
import numpy as np
import h5py
from scipy.integrate import cumtrapz
from numpy.matlib import repmat

np.seterr(divide='ignore', invalid='ignore')
clight = 299792458
m_proton=938.272046e6  # eV/c0**2
e_over_m_proton=9.580e7  # C/kg


def beam_converter(input_type, input_value, z_over_A=0):
    """Mutually convert beam velocity dependent values.
    
    Args:
        input_type: "beta", "gamma", "p_over_A", Wkin_over_A", "Brho"
        input_value: Corresponding Value.
            - p_over_A in eV/c
            - Wkin_over_A in eV (equivalent to specific energy of nucleus in eV/u)
            - Brho in Tm
        z_over_A: (#protons - #electrons) / #nucleons
            In case of fully stripped ions, z==Z
            
    Returns:
        beta: particle velocity / c
        gamma: relativistic factor
        p_over_A: momentum per nucleon, in eV/c
        Wkin_over_A: Kinetic energy, in eV
        Brho: Magnetic rigidity, in Tm

    Examples:
        >>> Z = 1
        >>> A = 2
        >>> beta, gamma, p_over_A, Wkin_over_A, Brho = beam_converter('p_over_A', 970e6/A, Z/A)
        >>> print("beta={:.3f}, gamma={:.3f}, p={:.3f}MeV/c, Ekin={:.3f}MeV, Brho={:.3f}Tm"
        ...     .format(beta, gamma, p_over_A*A/1e6, Wkin_over_A*A/1e6, Brho))
        beta=0.459, gamma=1.126, p=970.000MeV/c, Ekin=235.876MeV, Brho=3.235Tm
    """
    
    # go backwards
    if input_type == 'beta':
        beta = input_value
    elif input_type == 'gamma':
        gamma = input_value
        beta = np.sqrt(1-1/gamma**2)
    elif input_type == 'p_over_A':
        p_over_A = input_value
        gamma_times_beta = p_over_A/m_proton
        beta = 1/np.sqrt(1+1/gamma_times_beta**2)
    elif input_type == 'Wkin_over_A':
        Wkin_over_A = input_value
        gamma = Wkin_over_A/m_proton+1 
        beta = np.sqrt(1-1/gamma**2)
    elif input_type == 'Brho':
        if z_over_A == 0:
            raise ValueError('Please specify charge to calculate Brho.')
        Brho = input_value
        gamma_times_beta = Brho * z_over_A * e_over_m_proton / clight
        beta = 1/np.sqrt(1+1/gamma_times_beta**2)
    elif input_type == 'p':
        raise ValueError('Please specify momentum per nucleon, p_over_A.')
    elif input_type == 'Wkin':
        raise ValueError('Please specify energy per nucleon, Wkin_over_A.')
    else:
        raise ValueError('Unknown input type.')

    # go forward
    if  not 'gamma' in locals():
        gamma = (1-beta**2)**(-0.5)
    
    if  not 'p_over_A' in locals():
        p_over_A = gamma*beta*m_proton  # eV/c 
    
    if  not 'Wkin_over_A' in locals():
        Wkin_over_A = (gamma-1)*m_proton  # eV 
    
    if  not 'Brho' in locals():
        if z_over_A == 0:
            Brho = 0
        else:
            Brho = gamma*beta/z_over_A/e_over_m_proton*clight  # Tm
            
    return beta, gamma, p_over_A, Wkin_over_A, Brho


def hd5_import_path(path):
    """Parses all CST-hd5-files in the given folder."""

    f = []
    dEz_dx = []
    dEz_dy = []
    Ez = []
    
    for ii, filename in enumerate(os.listdir(path)):
        f_, z, Ez_, dEz_dx_, dEz_dy_, x0, y0 = h5_import_file(path+filename)
        f.append(f_)
        dEz_dx.append(dEz_dx_)
        dEz_dy.append(dEz_dy_)
        Ez.append(Ez_)

    f = np.array(f)
    dEz_dx = np.array(dEz_dx)
    dEz_dy = np.array(dEz_dy)
    Ez = np.array(Ez)
    
    return f, z, Ez, dEz_dx, dEz_dy, x0, y0
    
    
def h5_import_file(file_with_path):
    """Parse information from one single CST-hd5-file."""
    
    with h5py.File(file_with_path, 'r') as file:
        x0 = float(np.array(file['x0']))
        y0 = float(np.array(file['y0']))
        z = file['z'][:]
        f = float(np.array(file['f']))
        dEz_dx = file['xGrad'][:]
        dEz_dy = file['yGrad'][:]
        Ez = file['zComp'][:]
        
    return f, z, Ez, dEz_dx, dEz_dy, x0, y0


def matlab_import_file(path):
    """Parses a matlab .mat file.
	This is a personal function to read my old matlab results.
	
	Bernd Breitkreutz
	"""
    
    with h5py.File(path, 'r') as file:
        f = np.array(file.get("f"))[0]
        x0 = np.array(file.get("x0"))[0][0]
        aa = np.array(file.get("xGrad"))
        if type(aa[0][0]) == np.void:  # complex numbers are tuples
            dEz_dx = np.array([[a+1j*b for a,b in line] for line in aa]).transpose()
        else:
            dEz_dx = aa
        y0 = np.array(file.get("y0"))[0][0]
        aa = np.array(file.get("yGrad"))
        if type(aa[0][0]) == np.void:  # complex numbers are tuples
            dEz_dy = np.array([[a+1j*b for a,b in line] for line in aa]).transpose()
        else:
            dEz_dy = aa
        z = np.array(file.get("z")).transpose()[0]
        aa = np.array(file.get("zComp"))
        if type(aa[0][0]) == np.void:  # complex numbers are tuples
            Ez = np.array([[a+1j*b for a,b in line] for line in aa]).transpose()
        else:
            Ez = aa
    
    return f, z, Ez, dEz_dx, dEz_dy, x0, y0    


def rotate_phase(A, f, f1, f2):
    """Remove linear phase shift between two frequencies.
    A linear phase shift can be compensated by the cable length,
    or another choice of z=0-position inside the kicker. Since
	we a re usually interested in the maximum phase deviation
	in the desired frequency range, one should shift the first
	and last frequency point to the same phase.
    
    Args:
        A: Array of shape (len(f), len(z))
            The phase shift of last slide, A[:,-1], is removed.
        f: frequency
        f1: first frequency point
        f2: second frequency point
    Returns:
        out: Array of same shape as A.
            out[index(f1) and index(f2),-1] are on phase 0.
    """

    i1 = np.argmin(np.abs(f-f1))
    i2 = np.argmin(np.abs(f-f2))
    phi = np.unwrap(np.angle(A[:,-1]))
    phi1 = phi[i1]
    phi2 = phi[i2]
    _, nz = A.shape
    B = repmat(np.exp(-1j*f/(f2-f1)*(phi2-phi1)), nz, 1).transpose()
    out = A*B
    phi0 = np.angle(out[i1,-1])
    out *= np.exp(-1j*phi0)
    return out
    
    
def kickerLong(Ez, z, f, Pin_eff, beta, z_borders=[0, 0], Zc=50):    
    """Calculate longitudinal electric parameters of a kicker.
    
    Corresponding pick-up parameters are derived as well.
    
    Arrays are of the Numpy array type and of shape (len(f), len(z)). The
    integrated values are cumulative, to see the influence of propagating waves
    in the right hand side beam pipe. 
    Thus, the correct values are e.g. K(f)=K[:,-1]
   
    Formulas are from Glen Lambertson: 'Dynamic Devices -Pickups and
    Kickers', AIP Conference Proceedings 153, Vol. 2, 1987, DOI:
    10.1063/1.36380
    
    Args:
        Ez: Normal component of electric field. 
            Ez.shape == (len(f), len(z))
        z: Spatial dimension in beam direction.
        f: Frequency of the electric field.
        Pin_eff: Total applied rms-power to all ports. 
        beta: beam velocity, divided by speed of light.
        z_borders: Integration limits. Default is the complete z-array.
    
    Returns:
        Rshunt: R|T|^2, shunt impedance for the given beta
            $$\overline P_{in}=\frac{1}{2}\frac{|\Delta W / q|^2}{R|T|^2}$$
            or
            $$R |T|^2=Z_c |K|^2$$
        K: Kicker constant, i.e. beam voltage induced by 1 volt at the terminal. 
            $$K=\frac{V}{V_K}$$
        ZP: Pickup transfer impedance. Terminal voltage induced by 1 amp of
            beam current.
            $$V_P=Z_PI_B.$$
            Derived with reciprocity theorem from kicker constant:
            $$Z_P=\frac{1}{2} Z_c K $$
        V: Energy change over charge (q=Z*e), i.e. the effective 
            beam voltage of a particle of finite velocity.
            $$V=\frac{\Delta W}{q}=\int e^{j\omega\frac{z}{\beta c_0}} E_z dz$$
        VK: Terminal voltage. Voltage amplitude in the cable that is connected 
            to the kicker, i.e. before all dividers. 
            $$V_K=\sqrt{2 Z_c \overline P_{in}}$$
        (V0, R, T) Properties for infinitely fast particles:
            - V0: Beam voltage as seen by an infinitely fast particle.
                $$V_0=\int E_z dz$$
            - R: Shunt impedance  as seen by an infinitely fast particle.
                $$\overline P_{in}=\frac{1}{2}\frac{|V_0^2|}{R}$$
            - T: Transit time factor, i.e. reduction factor of beam voltage due to 
                finite beam velocity.
                $$T=\frac{V}{V_0}$$
            
            
    2015-11-11 Bernd Breitkreutz (Matlab Version)
    2018 11-29 Bernd Breitkreutz (first Python Version)
    """

    nf = len(f)
    nz = len(z)
    
    if (z_borders[0]**2+z_borders[1]**2) < 1e-6:
        z_borders = [z[0], z[-1]]
    
    if not Ez.shape == (nf, nz):
        raise ValueError('Ez is not of correct shape, i.e. (len(f), len(z)).')
        
    if type(beta) == list:
        if len(beta) == 1:
            beta = beta[0]
        else:
            raise ValueError('Currently only single betas are supported.')
    
    Ez[:, z<z_borders[0]] = 0
    Ez[:, z>z_borders[1]] = 0
    
    k = 2*np.pi*f / (beta*clight)
    z_ = repmat(z, nf, 1)
    k_ = repmat(k, nz, 1).transpose()
    
    VK = np.sqrt(2 * Zc * Pin_eff)
    V0 = cumtrapz(Ez, x=z, initial=0)
    V = cumtrapz(np.exp(1j*k_*z_) * Ez, x=z, initial=0)
    K = V/VK
    Rshunt = Zc*np.abs(K)**2
    R = abs(V0)**2/(2*Pin_eff)
    T = V/V0
    ZP=1/2 * Zc * K
    
    return Rshunt, K, ZP, V, VK, (V0, R, T)


def kickerTrans(dEz_du, z, f, Pin_eff, beta, z_borders=[0, 0], Zc=50, extra_values=False):    
    """Calculate transverse electric parameters of a kicker.
    
    Corresponding pick-up parameters are derived as well.
    
    Arrays are of the Numpy array type and of shape (len(f), len(z)). The
    integrated values are cumulative, to see the influence of propagating waves
    in the right hand side beam pipe. 
    Thus, the correct values are e.g. K(f)=K[:,-1]
    
    Formulas are from Glen Lambertson: 'Dynamic Devices -Pickups and
    Kickers', AIP Conference Proceedings 153, Vol. 2, 1987, DOI:
    10.1063/1.36380
    
    Args:
        dEz_du: Transverse gradient of normal component of electric field. 
            u is the desired direction of the kick, i.e. x or y
            dEz_du.shape == (len(f), len(z))
        z: Spatial dimension in beam direction.
        f: Frequency of the electric field.
        Pin_eff: Total applied rms-power to all ports. 
        beta: beam velocity, divided by speed of light.
        z_borders: Integration limits. Default is the complete z-array.
        extra_values: Will present additional parameters. Not Implemented yet.
    
    Returns:
        Ru_shunt: Ru|T|^2, transverse shunt impedance for the given beta
            $$R_uT^2=Z_c |K_u|^2$$
        Ku: Transverse kicker constant, i.e. beam kick induced by 1 volt at the terminal. 
            $$K_u=-\frac{1}{jk_B}\frac{\partial K'_{||}}{\partial u}$$
            with
            $$K'_{||}=\frac{V}{V_K}$$
            $$K_u=j\frac{\beta c_0}{\omega}\frac{1}{V_K}\frac{\partial V}{\partial u}$$
        ZPu_prime: Transverse Pickup transfer impedance. Terminal voltage induced by 1 amp of
            beam current at 1m offset in u-direction.
            $$Z'_{P,u}=-j\frac{1}{2}\frac{\omega}{\beta c_0}Z_c K_u$$
        dV_over_du: Gradient of energy change over charge (q=Z*e), i.e. the gradient
            of the effective beam voltage of a particle of finite velocity.
            $$\frac{\partial V}{\partial u}=\int e^{j\omega\frac{z}{\beta c_0}} \frac{\partial E_z}{\partial u} dz$$
        VK: Terminal voltage. Voltage amplitude in the cable that is connected 
            to the kicker, i.e. before all dividers. 
            $$V_K=\sqrt{2 Z_c \overline P_{in}}$$
    
    Todo:
        extra_values:
            Tu
            Deltap_over_q
            Deltap_over_q0
            Ru
            
    2016-26-10 Bernd Breitkreutz (Matlab Version)
    2018-11-30 Bernd Breitkreutz (first Python Version)
    2019-01-14 Bernd Breitkreutz (corrected k -> k_B in Ku and ZPu_prime)
    """
    
    if extra_values:
        # extra_values will lead to one more output (tuple of additional values).
        # Thus, it is explicitly asked for it to guarantee downwards compatibility.
        raise NotImplementedError('Values like those for infinitely fast particles are not implemented yet.')
    
    nf = len(f)
    nz = len(z)
    
    if (z_borders[0]**2+z_borders[1]**2) < 1e-6:
        z_borders = [z[0], z[-1]]
    
    if not dEz_du.shape == (nf, nz):
        raise ValueError('dEz_du is not of correct shape, i.e. (len(f), len(z)).')
        
    if type(beta) == list:
        if len(beta) == 1:
            beta = beta[0]
        else:
            raise ValueError('Currently only single betas are supported.')
    
    dEz_du[:, z<z_borders[0]] = 0
    dEz_du[:, z>z_borders[1]] = 0
    
    k = 2*np.pi*f / (beta*clight)
    z_ = repmat(z, nf, 1)
    k_ = repmat(k, nz, 1).transpose()
    omg_ = repmat(2*np.pi*f, nz, 1).transpose()
    
    VK = np.sqrt(2 * Zc * Pin_eff)
    dV_over_du = cumtrapz(np.exp(1j*k_*z_) * dEz_du, x=z, initial=0)
    Ku = 1j*beta*clight/omg_*1/VK*dV_over_du
    Ru_shunt = Zc*np.abs(Ku)**2
    ZPu_prime = -1j/2*omg_/(beta*clight)*Zc*Ku

    return Ru_shunt, Ku, ZPu_prime, dV_over_du, VK



















