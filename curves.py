"""
Import/Export CST curves.


The data are in "CST XY Data Exchange Format V2", as copied from the "1D Results"-Folder in CST.

Currently, only single curves can be processed.

2019 03 29 Bernd Breitkreutz
"""


import numpy as np
import pyperclip

def paste():
    """Paste a single S-parameter curve from the clipboard."""
    content = pyperclip.paste()
    content = content.split('\n')
    head = content[:24]
    body = content[24:]
    data = [line[:-1].split('\t') for line in body[:-1]]
    data = np.asfarray(data,float)
    freq = data[:,0]
    cmplx = data[:,1]+1j*data[:,2]
    return head, data, freq, cmplx

def copy(head, data):
    """Copy a single S-parameter curve to the clipboard."""
    #data[:,1] = np.real(cmplx)
    #data[:,2] = np.imag(cmplx)
    body = np.asarray(data, str)
    body = [ '\t'.join(x)+'\r' for x in body]
    pyperclip.copy('\n'.join(head+body))

def new_label(head, label):
    """Change the label of an S-parameter curve."""
    head[6] = 'Curvelabel  = ' + label + '\r'
    
