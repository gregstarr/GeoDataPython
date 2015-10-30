#!/usr/bin/env python
"""
GeoData.py
Created on Thu Jul 17 12:46:46 2014

@author: John Swoboda
"""
from __future__ import division,absolute_import
import logging
from datetime import datetime
from pytz import UTC
from six import integer_types,string_types
import posixpath
from copy import deepcopy
import numpy as np
import scipy.interpolate as spinterp
import tables
from pandas import DataFrame
#
from . import CoordTransforms as CT
from .utilityfuncs import read_h5_main


VARNAMES = ['data','coordnames','dataloc','sensorloc','times','expdesc']

class GeoData(object):
    '''This class will hold the information for geophysical data.
    Variables
    data - This is a dictionary with strings for keys only. The strings are
    the given names of the data.
    coordnames - A string that holds the type of coordinate system.
    dataloc - A numpy array that holds the locations of the samples
    sensorloc - A numpy array with the WGS coordinates of the sensor.
    times - A numpy array that is holding the times associated with the measurements.
    expdesc - Freeform user string(s) holding experiment description'''
    def __init__(self,readmethod,inputs):
        if isinstance(readmethod,string_types):
            (self.data,self.coordnames,self.dataloc,self.sensorloc,self.times,self.expdesc) = inputs
        else:
            '''This will create an instance of the GeoData class by giving it a read method and the inputs in a tuple'''
            (self.data,self.coordnames,self.dataloc,self.sensorloc,self.times,self.expdesc) = readmethod(*inputs)
        # Assert that the data types are correct
        numerics = (np.ndarray,integer_types,float)
        assert isinstance(self.data,dict),"data needs to be a dictionary"
        assert isinstance(self.coordnames,string_types), "coordnames needs to be a string"
        assert isinstance(self.dataloc,numerics),"dataloc needs to be a numpy array"
        assert isinstance(self.sensorloc,numerics),"sensorloc needs to be a numpy array"
        assert isinstance(self.times,numerics),"times needs to be a numpy array"
        self.times = timerepair(self.times)

    def datanames(self):
        '''Returns the data names.'''
        return self.data.keys()

    def write_h5(self,filename):
        '''Writes out the structured h5 files for the class.
        inputs
        filename - The filename of the output.'''
        with tables.openFile(filename, mode = "w", title = "GeoData Out") as h5file:
            # get the names of all the variables set in the init function
            varnames = self.__dict__.keys()
            vardict = self.__dict__
            try:
                # XXX only allow 1 level of dictionaries, do not allow for dictionary of dictionaries.
                # Make group for each dictionary
                for cvar in varnames:
                    #group = h5file.create_group(posixpath.sep, cvar,cvar +'dictionary')
                    if isinstance(vardict[cvar],dict): # Check if dictionary
                        dictkeys = vardict[cvar].keys()
                        group2 = h5file.create_group('/',cvar,cvar+' dictionary')
                        for ikeys in dictkeys:
                            h5file.createArray(group2,ikeys,vardict[cvar][ikeys],'Static array')
                    else:
                        h5file.createArray('/',cvar,vardict[cvar],'Static array')
            except Exception as e: # catch *all* exceptions
                exit('problem writing ' + str(filename) + ' due to ' +str(e))

    #%% Time registration
    def timeregister(self,self2):
        """ Create a cell array which shows the overlap between two
        instances of GeoData.
        Inputs
        self2 - A GeoData object.
        Outputs
        outcell - A cellarray of vectors the same length as the time
        vector in self. Each vector will have the time indecies from
        the second GeoData object which overlap with the time indicie
        of the first object."""
        times1 = timerepair(self.times)
        times2 = timerepair(self2.times)
        outcell = [[] for i in range(times1.shape[0])]
        for k in range(times1.shape[0]):
            l = times1[k,:]

            list1 = np.argwhere(l[0]>times2[:,0])
            list2 = np.argwhere(l[1]<times2[:,1])
            if (list1.size==0) or (list2.size==0):
               continue
            ind1 = list1[-1][0]
            ind2 = list2[0][0]
            outcell[k]=np.arange(ind1,ind2+1).astype('int64')
        return outcell


    #%% Time augmentation
    def add_times(self,self2):
        """This method will combine the times and content of two instances of the GeoData class.
        The first object will be extendent in time."""
        datakeys = self.data.keys()
        assert set(datakeys) ==set(self2.data.keys()),'Data must have the same names.'
        # Look at the coordinate names
        assert self.coordnames==self2.coordnames,'Must be same coordinate same.'
        # Look at the data location
        a = np.ma.array(self.dataloc,mask=np.isnan(self.dataloc))
        blah = np.ma.array(self2.dataloc,mask=np.isnan(self2.dataloc))
        assert np.ma.allequal(a,blah),'Location points must be the same'

        # Look at the sensor location
        a = np.ma.array(self.sensorloc,mask=np.isnan(self.sensorloc))
        blah = np.ma.array(self2.sensorloc,mask=np.isnan(self2.sensorloc))
        assert np.ma.allequal(a,blah),'Sensor Locations must be the same'

        alltimes = np.vstack((timerepair(self.times),timerepair(self2.times)))

        #sort based off of start times
        s_ind = np.argsort(alltimes[:,0])
        self.times = alltimes[s_ind]

        for ikey in self.datanames():
            outarr = np.hstack((self.data[ikey],self2.data[ikey]))
            self.data[ikey] = outarr[:,s_ind]

    def timeslice(self,timelist,listtype=None):
        """ This method will return a copy of the object with only the desired points of time.
        Inputs
            timelist - This is a list of times in posix for the beginning time or a
                listing of array elements depending on the input of listtype.
            listtype - This is a string the input must be 'Array', for the input list
                to array elements or 'Time' for the times list to represent posix times.
                If nothing is entered thedefault is 'Array'."""
        if listtype is None:
            loclist = timelist
        elif listtype =='Array':
            loclist = timelist
        elif listtype == 'Time':
            ix = np.in1d(self.times[:,0],timelist)
            loclist = np.where(ix)[0]

        gd2 = self.copy()
        if gd2.times.ndim==1:
            gd2.times = gd2.times[loclist]
        elif gd2.times.ndim==2:
            gd2.times = gd2.times[loclist,:]
        else:
            raise TypeError('i only expect 1 or 2 dimensions for time')

        for idata in gd2.datanames():
            if isinstance(gd2.data[idata],DataFrame):
                gd2.data[idata] = gd2.data[idata][gd2.times] #data is a vector
            elif gd2.data[idata].ndim==2:
                gd2.data[idata] = gd2.data[idata][:,loclist]
            elif gd2.data[idata].ndim==3:
                gd2.data[idata] = gd2.data[idata][loclist,:,:]
            else:
                raise TypeError('unknown data shape for gd2 data')
        return gd2
#%% Satellite Data
    def issatellite(self):
        """Checks if the instance is satellite data. It will give true if the sensorloc array is all nans"""
        if np.all(np.isnan(self.sensorloc)):
            return True
        else:
            return False
#%% Changing data based on location
    def interpolate(self,new_coords,newcoordname,method='nearest',fill_value=np.nan,
                    twodinterp = False,ikey=None,beammask=True):
        """This method will take the data points in the dictionary data and spatially.
        interpolate the points given the new coordinates. The method of interpolation
        will be determined by the input parameter method.
        Input:
            new_coords - A Nlocx3 numpy array. This will hold the new coordinates that
            one wants to interpolate the data over.
            newcoordname - New Coordinate system that the data is being transformed into.
            method - A string. The method of interpolation curently only accepts 'linear',
            'nearest' and 'cubic'
            fill_value - The fill value for the interpolation.
        """
        assert new_coords.ndim==2 and new_coords.shape[1]==3

        curavalmethods = ('linear', 'nearest', 'cubic')
        interpmethods = ('linear', 'nearest', 'cubic')
        assert method in interpmethods,'method needs to be linear, nearest, cubic'
        assert method in curavalmethods, 'Must be one of the following methods: '+ str(curavalmethods)

        Nt = self.times.shape[0]
        NNlocs = new_coords.shape[0]
#        print NNlocs
        new_coordsorig = deepcopy(new_coords)
        curcoords = self.__changecoords__(newcoordname)
        # XXX Pulling axes where all of the elements are the same.
        # Probably not the best way to fix issue with two dimensional interpolation
        if twodinterp:
            firstel = new_coords[0]
            firstelold = curcoords[0]
            keepaxis = np.ones(firstel.shape, dtype=bool)
            for k in range(len(firstel)):
                curax = new_coords[:,k]
                curaxold = curcoords[:,k]
                keepaxis[k] = not (np.all(curax==firstel[k]) or np.all(curaxold==firstelold[k]))

            #if index is true, keep that column
            curcoords = curcoords[:,keepaxis]
            new_coords = new_coords[:,keepaxis]
            NNlocs = new_coords.shape[0]

        # Check to see if you're outputing all of the parameters
        if ikey is None or ikey not in self.data.keys():
            # Loop through parameters and create temp variable
            for iparam in self.data.keys():
                usepandas=True if isinstance(self.data[iparam],DataFrame) else False
                # won't it virtually always be float?
                New_param = np.empty((NNlocs,Nt))#,dtype=self.data[iparam].dtype)
                for itime,tim in enumerate(self.times):
                    if usepandas:
                        curparam = self.data[iparam][tim] #dataframe: columns are time in this case
                    else: #assume Numpy
                        if self.data[iparam].ndim==2: #assuming 2-D numpy array
                            curparam = self.data[iparam][:,itime]
                        elif self.data[iparam].ndim==3: # take the image out of the stack
                            curparam = self.data[iparam][itime,:,:].ravel()
                        else:
                            raise ValueError('incorrect data matrix shape')
#%% filter out bad (nan) data points/location for this time step
                    if iparam != 'optical':
                        dfmask = np.isfinite(curparam) & beammask
                        curparam = curparam[dfmask]
                        npmask=dfmask.values if usepandas else dfmask #have to do this for proper indexing of numpy arrays!
                        coordkeep = curcoords[npmask,:]
                    else:
                        coordkeep = curcoords

                    if len(coordkeep)>0: # at least one finite value
#%% this line can take an eternity
                        intparam = spinterp.griddata(coordkeep,curparam,new_coords,method,fill_value)
#%%
                    else: # no finite values
                        logging.warning('No {} data available at {}'.format(iparam,datetime.fromtimestamp(tim[0],tz=UTC)))
                        intparam = np.nan
                    New_param[:,itime] = intparam
                self.data[iparam] = New_param


            self.dataloc = new_coordsorig
            self.coordnames=newcoordname
        else:
            New_param = np.zeros((NNlocs,Nt),dtype=self.data[ikey].dtype)
            for itime in range(Nt):
                curparam =self.data[ikey][:,itime]
                datakeep = ~np.isnan(curparam)
                curparam = curparam[datakeep]
                coordkeep = curcoords[datakeep]
                intparam = spinterp.griddata(coordkeep,curparam,new_coords,method,fill_value)
                New_param[:,itime] = intparam
            return New_param

    def __changecoords__(self,newcoordname):
        """This method will change the coordinates of the data to the new coordinate
        system before interpolation.
        Inputs:
        newcoordname: A string that holds the name of the new coordinate system everything is being changed to.
        outputs
        outcoords: A new coordinate system where each row is a coordinate in the new system.
        """
        if self.coordnames.lower()=='spherical' and newcoordname.lower()=='cartesian':
            return CT.sphereical2Cartisian(self.dataloc)
        if self.coordnames.lower()=='cartesian'and newcoordname.lower()=='spherical':
            return CT.cartisian2Sphereical(self.dataloc)
        if self.coordnames.lower()==newcoordname.lower():
            return self.dataloc
        raise ValueError('Wrong inputs for coordnate names was given.')

    def checkcoords(self,newcoords,coordname):
        """ This method checks to see if all of the coordiantes are in the class instance.
        inputs
        pltdict - A dictionary with keys that represent each of the dimensions of
        the data. For example 0 is the x axis 1 is the y axis 2 is the z axis. The values
        are numpy arrays.
        coordname - This is coordinate names of the input directory."""
        origcoords = self.dataloc
        origcoordname = self.coordnames
        if coordname!=origcoordname:
            return False
        for irow in newcoords:
            if not np.any(np.all(origcoords==irow,axis=1)):
                return False
        return True

    def datareducelocation(self,newcoords,coordname,key=None):
        """ This method takes a list of coordinates and finds what instances are in
        the set of locations for the instance of the class.
        newcoords -A numpy array where each row is a coordinate that the user desires to keep.
        coordname - This is coordinate names of the input directory.
        key - The name of the data that the user wants extracted"""
        assert(self.coordnames.lower()==coordname.lower())

        reorderlist = np.zeros(len(newcoords)).astype('int64')
        for irown,irow in enumerate(newcoords):
            reorderlist[irown]=np.where(np.all(self.dataloc==irow,axis=1))[0][0]
        if key is None:
            for ikey in self.datanames():
                self.data[ikey]= self.data[ikey][reorderlist]
        else:
            return self.data[key][reorderlist]

    #%% General tools
    def changedata(self,dataname,newname,func,params=(),rm_old=True):
        """ This method will take a set of data out of the instance of this class and apply
        the function func to it with the extra parameters params.
        Inputs:
        dataname - A string that is one of the datanames.
        newname - A string for the changed data that it will be known as from now on.
        func - The function used to change the data.
        params - (default - ()) Any extra parameters that are needed for the function.
        rm_old - (default - True) A flag that if set to True will remove the old data."""

        assert dataname in self.data.keys(),"Incorrect data name used."
        self.data[newname]=func(self.data[dataname],*params)
        if rm_old:
            del self.data[dataname]
    def copy(self):
        return GeoData(copyinst,[self])



    @staticmethod
    def read_h5(filename):
        """ Static method for this"""
        return GeoData(read_h5_main,[filename])

    def __eq__(self,self2):
        '''This is the == operator. '''
        # Check the data dictionary
        datakeys = self.data.keys()
        if set(datakeys) !=set(self2.data.keys()):
            return False

        for ikey in datakeys:
            a = np.ma.array(self.data[ikey],mask=np.isnan(self.data[ikey]))
            b = np.ma.array(self2.data[ikey],mask=np.isnan(self2.data[ikey]))
            if not np.ma.allequal(a,b):
                return False
        # Look at the coordinate names
        if self.coordnames!=self2.coordnames:
            return False
        # Look at the data location
#        pdb.set_trace()
        a = np.ma.array(self.dataloc,mask=np.isnan(self.dataloc))
        blah = np.ma.array(self2.dataloc,mask=np.isnan(self2.dataloc))
        if not np.ma.allequal(a,blah):
            return False
        # Look at the sensor location
        a = np.ma.array(self.sensorloc,mask=np.isnan(self.sensorloc))
        blah = np.ma.array(self2.sensorloc,mask=np.isnan(self2.sensorloc))
        if not np.ma.allequal(a,blah):
            return False
        # Look at the times
        a = np.ma.array(self.times,mask=np.isnan(self.times))
        blah = np.ma.array(self2.times,mask=np.isnan(self2.times))
        if not np.ma.allequal(a,blah):
            return False

        return True


    def __ne__(self,self2):
        '''This is the != operator. '''
        return not self.__eq__(self2)
#%%
def copyinst(obj1):
    return(obj1.data.copy(),
           (obj1.coordnames+'.')[:-1],
           obj1.dataloc.copy(),
           obj1.sensorloc.copy(),
           obj1.times.copy(),
           obj1.expdesc)

def is_numeric(obj):
    return isinstance(obj,(integer_types,float))
    #attrs = ['__add__', '__sub__', '__mul__', '__div__', '__pow__']
    #return all(hasattr(obj, attr) for attr in attrs)
# TODO might want to make this private method
# currently just give this to the init function and it will create a class instance.


def pathparts(path):
    ''' This function will give a list of paths for a posix path string. It is mainly used
    for h5 files
    Inputs
    path - A posix type path string.
    Outputs
    A list of strings of each part of the path.'''
    components = []
    while True:
        (path,tail) = posixpath.split(path)
        if tail == "":
            components.reverse()
            return components
        components.append(tail)

def timerepair(timear):
    if timear.ndim==2:
        if timear.shape[1] ==2:
            return timear
        timear = timear.ravel()
    if timear.size==1:
        # XXX Using this for my simulator program because old data does not have end times.
        logging.warning('Timear is only of size 1. Making second element that is 60 seconds ahead of the original')
        return  np.array([[timear[0],timear[0]+60]])

    avdiff = np.diff(timear).mean()
    timear2 = np.roll(timear,-1)
    timear2[-1]=timear2[-2]+avdiff
    return np.column_stack((timear,timear2))
