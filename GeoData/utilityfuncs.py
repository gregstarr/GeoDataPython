#!/usr/bin/env python
"""
Created on Thu Sep 11 15:29:27 2014

@author: John Swoboda
"""
from __future__ import division,absolute_import
import pdb
import numpy as np
import tables as tb
import h5py
import posixpath
import scipy as sp
import tables
from pandas import DataFrame
from warnings import warn,simplefilter
simplefilter('ignore', tables.NaturalNameWarning) #b/c of po+ field in full ISR data files
#
from . import CoordTransforms as CT

usepandas = True #20x speedup vs CPython

VARNAMES = ['data','coordnames','dataloc','sensorloc','times']

def readMad_hdf5 (filename, paramstr): #timelims=None
    """@author: Michael Hirsch / Anna Stuhlmacher
    madgrigal h5 read in function for the python implementation of GeoData for Madrigal Sondrestrom data
    Input:
    filename path to hdf5 file
    list of parameters to look at written as strings
    Returns:
    dictionary with keys are the Madrigal parameter string, the value is an array
    rows are unique data locations (data_loc) = (rng, azm, el1)
    columns are unique times

    Here we use Pandas DataFrames internally to speed the reading process by 20+ times,
    while still passing out Numpy arrays
    """
    #open hdf5 file
    with tb.openFile(filename, mode = "r", title = 'Sondrestrom1') as files:
        all_data = files.getNode('/Data/Table Layout').read()
        sensor_data = files.getNode('/Metadata/Experiment Parameters').read()


    instrument = str(sensor_data[0][1]) #instrument type string, comes out as bytes so cast to str
    if "Sondrestrom" in instrument:
        radar = 1
        print("Sondrestrom data")
    elif "Poker Flat" in instrument:
        radar = 2
        print("PFISR data")
    elif "Resolute Bay" in instrument:
        radar = 3
        print ("RISR data")
    else:
        exit("Error: Radar type "+str(instrument) +" not supported by program in this version.")

    # get the data location (range, el1, azm)
    if radar == 1:
        irng = 'gdalt'
    elif radar in (2,3):
        irng = 'range'

    filt_data = DataFrame(columns=['range','az','el','ut1','ut2'])
    try:
        filt_data['range'] = all_data[irng]
    except ValueError: pass
    try:
        filt_data['az'] = all_data['azm']
    except ValueError: pass
    try:
        filt_data['el'] = all_data['elm']
    except ValueError: pass

    filt_data['ut1'] = all_data['ut1_unix']
    filt_data['ut2'] = all_data['ut2_unix']

    for p in paramstr:
        filt_data[p] = all_data[p]

#%% SELECT
    filt_data.dropna(axis=0,how='any',subset=['range','az','el'],inplace=True)

    #create list of unique data location lists
    dataloc = filt_data[['range','az','el']].drop_duplicates()
    uniq_times = filt_data['ut1'].drop_duplicates().values


    #initialize and fill data dictionary with parameter arrays
    #notnan = filt_data.index
    if not usepandas:
        all_loc=filt_data[['range','az','el']].values.tolist()
        all_times = filt_data['ut1'].values.tolist()
        dataloclist = dataloc.values.tolist()
        uniq_timeslist = uniq_times = filt_data['ut1'].drop_duplicates().values.tolist()
        maxcols = len(uniq_times);  maxrows = len(dataloc)

    data = {}
    for p in paramstr:
        if not p in all_data.dtype.names:
            warn('{} is not a valid parameter name.'.format(p))
            continue

        if usepandas:
        # example of doing via numpy
        # filt_data has already been filtered for time and location with the isr parameter(s) riding along.
         #Just reshape it!
            #TODO take off the .values to pass the DataFrame
            data[p] = DataFrame(data=filt_data[p].reshape((dataloc.shape[0],uniq_times.shape[0]),order='F'),
                                               columns=uniq_times).values
        else:
            #example with CPython
            vec = filt_data[p].values #list of parameter pulled from all_data
            arr = np.empty([maxrows,maxcols]) #converting the tempdata list into array form

            for t in range(vec.size):
                #row
                row = dataloclist.index(all_loc[t])
                #column-time
                col = uniq_timeslist.index(all_times[t])
                arr[row][col] = vec[t]
            data[p] = arr

        #example of doing by MultiIndex
#        data[p]= DataFrame(index=[dataloc['range'],dataloc['az'],dataloc['el']],
#                            columns=uniq_times)
#        for i,qq in filt_data.iterrows():
#            ci = qq[['range','az','el']].values
#            data[p].loc[ci[0],ci[1],ci[2]][qq['ut1'].astype(int)] = qq[p]


    #get the sensor location (lat, long, rng)
    lat,lon,sensor_alt = sensor_data[7][1],sensor_data[8][1],sensor_data[9][1]
    sensorloc = np.array([lat,lon,sensor_alt], dtype=float) #they are bytes so we NEED float!
    coordnames = 'Spherical'
    #TODO temporarily passing dataloc as Numpy array till rest of program is updated to Pandas
    return (data,coordnames,dataloc.values,sensorloc,uniq_times)

def readSRI_h5(filename,paramstr,timelims = None):
    '''This will read the SRI formated h5 files for RISR and PFISR.'''
    coordnames = 'Spherical'
    h5file=tables.openFile(filename)
    # Set up the dictionary to find the data
    pathdict = {'Ne':('/FittedParams/Ne',None),'dNe':('/FittedParams/Ne',None),
                'Vi':('/FittedParams/Fits',(0,3)),'dVi':('/FittedParams/Errors',(0,3)),
                'Ti':('/FittedParams/Fits',(0,1)),'dTi':('/FittedParams/Errors',(0,1)),
                'Te':('/FittedParams/Fits',(-1,1)),'Ti':('/FittedParams/Errors',(-1,1))}

    # Get the times and time lims
    times = h5file.getNode('/Time/UnixTime').read()
    nt = times.shape[0]
    if timelims is not None:
        timelog = times[:,0]>= timelims[0] and times[:,1]<timelims[1]
        times = times[timelog,:]
        nt = times.shape[0]
    # get the sensor location
    lat = h5file.getNode('/Site/Latitude').read()
    lon = h5file.getNode('/Site/Longitude').read()
    alt = h5file.getNode('/Site/Altitude').read()
    sensorloc = np.array([lat,lon,alt])
    # Get the locations of the data points
    rng = h5file.getNode('/FittedParams/Range').read()/1e3
    angles = h5file.getNode('/BeamCodes').read()[:,1:2]
    nrng = rng.shape[1]
    repangles = np.tile(angles,(1,2.0*nrng))
    allaz = repangles[:,::2]
    allel = repangles[:,1::2]
#   TODO dataloc = DataFrame(index=times,
#                              {'rng':rng.ravel(),
#                               'allaz':allaz.ravel(),'allel':allel.ravel()})
    dataloc =np.vstack((rng.ravel(),allaz.ravel(),allel.ravel())).transpose()
    # Read in the data
    data = {}
    for istr in paramstr:
        if not istr in list(pathdict.keys()):
            warn(istr + ' is not a valid parameter name.')

            continue
        curpath = pathdict[istr][0]
        curint = pathdict[istr][-1]

        if curint is None:

            tempdata = h5file.getNode(curpath).read()
        else:
            tempdata = h5file.getNode(curpath).read()[:,:,:,curint[0],curint[1]]
        data[istr] = np.array([tempdata[iT,:,:].flatten() for iT in range(nt)]).transpose()
    h5file.close()
    return (data,coordnames,dataloc,sensorloc,times)

def read_h5_main(filename):
    '''
    Read in the structured h5 file.
    use caution with this function -- indexing dicts is less safe
    because the index order of dicts is not deterministic.
    '''
    with tb.openFile(filename) as h5file:
        output={}
        # Read in all of the info from the h5 file and put it in a dictionary.
        for group in h5file.walkGroups(posixpath.sep):
            output[group._v_pathname]={}
            for array in h5file.listNodes(group, classname = 'Array'):
                output[group._v_pathname][array.name]=array.read()

    #pdb.set_trace()
    # find the base paths which could be dictionaries or the base directory
#    outarr = [pathparts(ipath) for ipath in output.keys() if len(pathparts(ipath))>0]
    outlist = {}
    basekeys  = output[posixpath.sep].keys()
    # Determine assign the entries to each entry in the list of variables.
    # Have to do this in order because of the input being a list instead of a dictionary

    #dictionary
    for ipath in output:
        if ipath[1:] in VARNAMES:
            outlist[ipath[1:]] = output[ipath]
            continue
    # for non-dicitonary
    for k in basekeys:
        if k in VARNAMES:
            # Have to check for MATLAB type strings, for some reason python does not like to register them as strings
            curdata = output['/'][k]
            if isinstance(curdata,np.ndarray):
                if curdata.dtype.kind=='S':
                    curdata=str(curdata)
            outlist[k] = curdata

    return outlist

def pathparts(path):
    ''' '''
    components = []
    while True:
        (path,tail) = posixpath.split(path)
        if tail == "":
            components.reverse()
            return components
        components.append(tail)

def readOMTI(filename, paramstr):
    """
    The data paths are known a priori, so read directly ~10% faster than pytables
    """
    with h5py.File(filename,'r') as f:
        optical = {'optical':f['data/optical'].value} #for legacy API compatibility
        dataloc = CT.enu2cartisian(f['dataloc'].value)
        coordnames = 'Cartesian'
        sensorloc = f['sensorloc'].value.squeeze()
        times = f['times'].value

    return optical, coordnames, dataloc, sensorloc, times

def readIono(iono):
    """ This function will bring in instances of the IonoContainer class into GeoData.
    this is using the set up from my own code"""
    pnames = iono.Param_Names
    Param_List = iono.Param_List
    pdb.set_trace()
    (nloc,nt) = Param_List.shape[:2]
    if type(pnames) == sp.ndarray:
        if pnames.ndim>1:
            ionkeys = pnames.flatten()
            Param_List = sp.reshape(Param_List,(nloc,nt,len(ionkeys)))
        else:
            ionkeys=pnames
    else:
        ionkeys=pnames
    paramdict = {ikeys:Param_List[:,:,ikeyn] for ikeyn, ikeys in enumerate(ionkeys)}
    Nis = {}
    Tis = {}
    # Add Ti
    for ikey in ionkeys:
        if 'Ti_' ==ikey[:3]:
            Tis[ikey[3:]] = paramdict[ikey]
        elif 'Ni_' ==ikey[:3]:
            Nis[ikey[3:]] = paramdict[ikey]
    Nisum = sp.zeros((nloc,nt),dtype=Param_List.dtype)
    Ti = sp.zeros_like(Nisum)
    for ikey in Tis.keys():
        Ti =Tis[ikey]*Nis[ikey] +Ti
        Nisum = Nis[ikey]+Nisum
    if len(Ti)!=0:
        paramdict['Ti'] = Ti/Nisum
    if iono.Coord_Vecs == ['r','theta','phi']:
        coordnames = 'Spherical'
        coords = iono.Sphere_Coords
    elif iono.Coord_Vecs == ['x','y','z']:
        coordnames = 'Cartesian'
        coords = iono.Cart_Coords

    return (paramdict,coordnames,coords,sp.array(iono.Sensor_loc),iono.Time_Vector)

#data, coordnames, dataloc, sensorloc, times = readMad_hdf5('/Users/anna/Research/Ionosphere/2008WorldDaysPDB/son081001g.001.hdf5', ['ti', 'dti', 'nel'])
