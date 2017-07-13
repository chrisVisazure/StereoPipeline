#!/usr/bin/env python
# -*- coding: utf-8 -*-
# __BEGIN_LICENSE__
#  Copyright (c) 2009-2013, United States Government as represented by the
#  Administrator of the National Aeronautics and Space Administration. All
#  rights reserved.
#
#  The NGT platform is licensed under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance with the
#  License. You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# __END_LICENSE__

'''
Tool for downloading IceBridge data
'''

import sys, os, re, subprocess, optparse, logging
import icebridge_common
import httplib
from urlparse import urlparse

logger = logging.getLogger(__name__)

# The path to the ASP python files
basepath    = os.path.abspath(sys.path[0])
pythonpath  = os.path.abspath(basepath + '/../Python')  # for dev ASP
libexecpath = os.path.abspath(basepath + '/../libexec') # for packaged ASP
sys.path.insert(0, basepath) # prepend to Python path
sys.path.insert(0, pythonpath)
sys.path.insert(0, libexecpath)

import asp_system_utils

asp_system_utils.verify_python_version_is_supported()

# Prepend to system PATH
os.environ["PATH"] = libexecpath + os.pathsep + os.environ["PATH"]
os.environ["PATH"] = basepath    + os.pathsep + os.environ["PATH"]

#------------------------------------------------------------------------------

# Constants
LIDAR_TYPES = ['lvis', 'atm1', 'atm2']

def checkIfUrlExists(url):
    '''Return true if the given IceBrige folder URL is valid'''
    p    = urlparse(url)
    conn = httplib.HTTPConnection(p.netloc)
    conn.request('HEAD', p.path)
    resp = conn.getresponse()
    # Invalid pages return 404, valid pages should return one of the numbers below.
    #print 'URL response = ' + str(resp.status)
    return (resp.status == 403) or (resp.status == 301)

def makeYearFolder(year, site):
    '''Generate part of the URL.  Only used for images.'''
    return str(year) + '_' + site + '_NASA'

def makeDateFolder(year, month, day, fileType):
    '''Generate part of the URL.'''

    if fileType == 'image':
        datePart = ('%02d%02d%04d') % (month, day, year)
        return datePart +'_raw'
    else: # Used for all other cases
        datePart = ('%04d.%02d.%02d') % (year, month, day)
        return datePart

def getFolderUrl(year, month, day, site, fileType):
    '''Get full URL to the location where the files are kept.'''
    
    if fileType == 'image':
        base = 'https://n5eil01u.ecs.nsidc.org/ICEBRIDGE_FTP/IODMS0_DMSraw_v01'
        yearFolder = makeYearFolder(year, site)
        dateFolder = makeDateFolder(year, month, day, fileType)
        folderUrl  = os.path.join(base, yearFolder, dateFolder)
        return folderUrl
    # The other types share more formatting
    if fileType == 'ortho':
        base = 'https://n5eil01u.ecs.nsidc.org/ICEBRIDGE/IODMS1B.001'       
    if fileType == 'dem':
        base = 'https://n5eil01u.ecs.nsidc.org/ICEBRIDGE/IODMS3.001'
    if fileType == 'lvis':
        base = 'https://n5eil01u.ecs.nsidc.org/ICEBRIDGE/ILVIS2.001/'
    if fileType == 'atm1':
        base = 'https://n5eil01u.ecs.nsidc.org/ICEBRIDGE/ILATM1B.001/'
    if fileType == 'atm2':
        base = 'https://n5eil01u.ecs.nsidc.org/ICEBRIDGE/ILATM1B.002/'
    dateFolder = makeDateFolder(year, month, day, fileType)
    folderUrl  = os.path.join(base, dateFolder)
    return folderUrl


def fileExists(path):
    '''Make sure file exists and is non-empty'''
    return os.path.exists(path) and (os.path.getsize(path) > 0)

def fetchAndParseIndexFile(folderUrl, path, parsedPath, fileType):
    '''Retrieve the index file for a folder of data and create
    a parsed version of it that contains frame number / filename pairs.'''

    # Set up the command
    cookiePaths = ' -b ~/.urs_cookies -c ~/.urs_cookies '
    curlOpts    = ' -n -L '
    curlPath = asp_system_utils.which("curl")
    #logger.info("Using curl from " + curlPath)
    cmd = curlPath + ' ' + cookiePaths + curlOpts + folderUrl + ' > ' + path
    # Download the file
    logger.info(cmd)
    p = subprocess.Popen(cmd, shell=True)
    os.waitpid(p.pid, 0)
    
    # Find all the file names in the index file and
    #  dump them to a new index file
    logger.info('Extracting file name list from index.html file...')
    with open(path, 'r') as f:
        indexText = f.read()

    # Extract just the file names
    fileList = [] # ensure initialization
    if fileType == 'image':
        fileList = re.findall(">[0-9_]*.JPG", indexText, re.IGNORECASE)
    if fileType == 'ortho':
        fileList = re.findall(">DMS\w*.tif<", indexText, re.IGNORECASE) 
    if fileType == 'dem':
        fileList = re.findall(">IODMS\w*DEM.tif", indexText, re.IGNORECASE)
    if fileType == 'lvis':
        fileList = re.findall(">ILVIS\w+.TXT", indexText, re.IGNORECASE)
    if fileType == 'atm1':
        fileList = re.findall(">ILATM1B[0-9_]*.ATM4\w+.qi", indexText, re.IGNORECASE)
        #                      >ILATM1B_20111018_145455.ATM4BT4.qi
        #   or                 >ILATM1B_20091016_165112.atm4cT3.qi
    if fileType == 'atm2':
        # Match ILATM1B_20160713_195419.ATM5BT5.h5 
        fileList = re.findall(">ILATM1B[0-9_]*.ATM\w+.h5", indexText, re.IGNORECASE)
    
    # For each entry that matched the regex, record: the frame number and the file name.
    with open(parsedPath, 'w') as f:
        for filename in fileList:
            # Get rid of '>' and '<'
            filename = filename.replace(">", "")
            filename = filename.replace("<", "")
            frame = icebridge_common.getFrameNumberFromFilename2(filename)
            f.write(str(frame) + ', ' + filename + '\n')

def main(argsIn):

    # Command line parsing
    try:
        usage  = "usage: fetch_icebridge_data.py [options] output_folder"
        parser = optparse.OptionParser(usage=usage)

        parser.add_option("--year",  dest="year", type='int', default=None,
                          help="Number of processes to use (default program tries to choose best)")
        parser.add_option("--month",  dest="month", type='int', default=None,
                          help="Number of processes to use (default program tries to choose best)")
        parser.add_option("--day",  dest="day", type='int', default=None,
                          help="Number of processes to use (default program tries to choose best)")
        parser.add_option("--yyyymmdd",  dest="yyyymmdd", default=None,
                          help="Specify the year, month, and day in one YYYYMMDD string.")
        parser.add_option("--site",  dest="site", default=None,
                          help="Name of the location of the images (AN or GR)")
        
        parser.add_option("--start-frame",  dest="startFrame", type='int', default=None,
                          help="Frame number or start of frame sequence")
        parser.add_option("--stop-frame",  dest="stopFrame", type='int', default=None,
                          help="End of frame sequence to download.")
        parser.add_option("--all-frames", action="store_true", dest="allFrames", default=False,
                          help="Fetch all frames for this flight.")
        
        parser.add_option("--dry-run", action="store_true", dest="dryRun", default=False,
                          help="Just print the image/ortho/dem download commands.")

        parser.add_option("--zip-if-all-fetched", action="store_true", dest="zipIfAllFetched", default=False,
                          help="This will fail if not all the required files exist.")
        
        parser.add_option("--refetch-index", action="store_true", dest="refetchIndex", default=False,
                          help="Force refetch of the index file.")

        parser.add_option("--type",  dest="type", default='image',
                          help="File type to download ([image], ortho, dem, lidar)")

        # This call handles all the parallel_mapproject specific options.
        (options, args) = parser.parse_args(argsIn)

        if len(args) != 1:
            logger.info('Error: Missing output folder.\n' + usage)
            return -1
        outputFolder = os.path.abspath(args[0])

        # Handle unified date option
        if options.yyyymmdd:
            options.year  = int(options.yyyymmdd[0:4])
            options.month = int(options.yyyymmdd[4:6])
            options.day   = int(options.yyyymmdd[6:8])

        if not options.stopFrame:
            options.stopFrame = options.startFrame
        
        # Error checking
        if (not options.year) or (not options.month) or (not options.day):
            logger.error('Error: year, month, and day must be provided.\n' + usage)
            return -1
        
        # Ortho and DEM files don't need this information to find them.
        if (options.type == 'image') and not (options.site == 'AN' or options.site == 'GR'):
            logger.error('Error, site must be AN or GR for images.\n' + usage)
            return -1

        KNOWN_TYPES = ['image', 'ortho', 'dem', 'lidar']
        if not (options.type.lower() in KNOWN_TYPES):
            logger.error('Error, type must be image, ortho, or dem.\n' + usage)
            return -1

    except optparse.OptionError, msg:
        raise Exception(msg)

    # Verify that required files exist
    home = os.path.expanduser("~")
    if not (os.path.exists(home+'/.netrc') and os.path.exists(home+'/.urs_cookies')):
        logger.error('Missing a required authentication file!  See instructions here:\n' +
                     '    https://nsidc.org/support/faq/what-options-are-available-bulk-downloading-data-https-earthdata-login-enabled')
        return -1
    
    logger.info('Creating output folder: ' + outputFolder)
    os.system('mkdir -p ' + outputFolder)  

    # This URL contains all of the files
    if options.type == 'lidar':
        options.allFrames = True # For lidar, always get all the frames!
        
        # For lidar, the data can come from one of three sources.
        for lidar in LIDAR_TYPES:
            folderUrl = getFolderUrl(options.year, options.month, options.day, options.site, lidar)
            logger.info('Checking lidar URL: ' + folderUrl)
            if checkIfUrlExists(folderUrl):
                logger.info('Found match with lidar type: ' + lidar)
                options.type = lidar
                break
            if lidar == LIDAR_TYPES[-1]: # If we tried all the lidar types...
                if options.zipIfAllFetched:
                    # Have no choice here, will study this later
                    logger.info('WARNING: Could not find any lidar data for the given date!')
                else:
                    logger.error('ERROR: Could not find any lidar data for the given date!')
                    return -1
    else: # Other cases are simpler
        folderUrl = getFolderUrl(options.year, options.month, options.day, options.site, options.type)
    #logger.info('Fetching from URL: ' + folderUrl)
    
    # Fetch the index for this folder
    filename        = options.type + '_index.html'
    indexPath       = os.path.join(outputFolder, filename)
    parsedIndexPath = indexPath + '.csv'
    if options.refetchIndex:
        os.system('rm -f ' + indexPath)
        os.system('rm -f ' + parsedIndexPath)

    if fileExists(parsedIndexPath):
        logger.info('Already have the index file ' + indexPath + ', keeping it.')
    else:
        fetchAndParseIndexFile(folderUrl, indexPath, parsedIndexPath, options.type)
    
    if options.zipIfAllFetched and not fileExists(parsedIndexPath):
        if options.type != 'dem' and options.type != 'lidar': # be gentle about these
            raise Exception('Cannot zip, missing file: ' + parsedIndexPath)
        else:
            # The DEMs need not be there
            logger.info('Warning: Missing index file: ' + parsedIndexPath)

    # Files that we will fetch. We will check the success later. 
    allFilesToFetch=[]
    
    # Store file information in a dictionary
    # - Keep track of the earliest and latest frame
    logger.info('Reading file list from ' + parsedIndexPath)
    frameDict = {}
    firstFrame = icebridge_common.getLargestFrame()    # start big
    lastFrame  = icebridge_common.getSmallestFrame()   # start small
    with open(parsedIndexPath, 'r') as f:
        for line in f:
            parts       = line.strip().split(',')
            frameNumber = int(parts[0])
            frameDict[frameNumber] = parts[1].strip()
            if frameNumber < firstFrame:
                firstFrame = frameNumber
            if frameNumber > lastFrame:
                lastFrame = frameNumber

    if options.allFrames:
        options.startFrame = firstFrame
        options.stopFrame  = lastFrame

    # There is always a chance that not all requested frames are available.
    # That is particularly true for Fireball DEMs. Instead of failing,
    # just download what is present and give a warning. 
    if options.startFrame not in frameDict:
        logger.info("Warning: Frame " + str(options.startFrame) + " is not found in this flight.")
                    
    if options.stopFrame and (options.stopFrame not in frameDict):
        logger.info("Warning: Frame " + str(options.stopFrame) + " is not found in this flight.")
                    
    # Init the big curl command
    # - We will add multiple file targets and then execute the command
    cookiePaths = ' -b ~/.urs_cookies -c ~/.urs_cookies '
    curlPath = asp_system_utils.which("curl")
    #logger.info("Using curl from " + curlPath)
    baseCmd     = curlPath + ' -n -L ' + cookiePaths
    curlCmd     = baseCmd
    
    # What is the maximum number of files that can be downloaded with one call?
    MAX_IN_ONE_CALL = 100
    
    # Loop through all found frames within the provided range
    currentFileCount = 0
    allFrames = sorted(frameDict.keys())
    lastFrame = ""
    if len(allFrames) > 0:
        lastFrame = allFrames[len(allFrames)-1]
        
    for frame in allFrames:
        if (frame >= options.startFrame) and (frame <= options.stopFrame):

            filename = frameDict[frame]

            # Some files have an associated xml file.
            # TODO: Don't DEMs also have an associated file, with some other exension? 
            currFilesToFetch = [filename]
            if (options.type in LIDAR_TYPES) or (options.type == 'ortho'): 
                currFilesToFetch.append( filename + '.xml')

            for filename in currFilesToFetch:    
                url        = os.path.join(folderUrl, filename)
                outputPath = os.path.join(outputFolder, filename)
                allFilesToFetch.append(outputPath)

                # This is very important. If something killed curl, it may leave incomplete
                # images.
                if options.zipIfAllFetched and icebridge_common.hasImageExtension(outputPath):
                    if fileExists(outputPath) and not icebridge_common.isValidImage(outputPath):
                        os.remove(outputPath)
                        logger.info('Wiped invalid image: ' + outputPath)
                    
                if not fileExists(outputPath):
                    # Add to the command
                    curlCmd += ' -O ' + url
                    currentFileCount += 1 # Number of files in the current download command
        
        # Download the indicated files when we hit the limit or run out of files
        if ((currentFileCount >= MAX_IN_ONE_CALL) or (frame == lastFrame)) and currentFileCount > 0:
            logger.info(curlCmd)
            if not options.dryRun:
                logger.info("Saving the data in " + outputFolder)
                p = subprocess.Popen(curlCmd, cwd=outputFolder, shell=True)
                os.waitpid(p.pid, 0)
            # Start command fresh for the next file
            currentFileCount = 0
            curlCmd = baseCmd


    # Verify for the last time that all files were fetched and are in good shape
    if options.zipIfAllFetched:
        for outputPath in allFilesToFetch:
            if not fileExists(outputPath): 
                raise Exception('Cannot zip, missing file: ' + outputPath)

            #continue # For debugging purposes
        
            if icebridge_common.hasImageExtension(outputPath):
                if not icebridge_common.isValidImage(outputPath):
                    os.remove(outputPath)
                    raise Exception('Found an invalid image. Cannot zip. ' +
                                    'Please rerun fetching. Will wipe the invalid image: ' +
                                    outputPath)
                else:
                    logger.info("Found valid image: " + outputPath)
                    

    return 0
    
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

