#!/usr/bin/python
# Filename: analyzer.py
"""
A event-driven analyzer abstraction, 
including low-level msg filter and high-level analyzer

Author: Yuanjie Li
"""

"""
    Analyzer 2.0 development plan

        Step 1: A query() interface with SQLlite

            - Backward compatability with Analyzer 1.0

        Step 2: replace logging with customized logger

        Step 3: A global analyzer repo to guarantee consistency

"""

from ..element import Element, Event
#from profile import *
import logging
import time
import datetime as dt

class MyFormatter(logging.Formatter):
    converter=dt.datetime.fromtimestamp
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            t = ct.strftime("%Y-%m-%d %H:%M:%S")
            s = "%s,%03d" % (t, record.msecs)
        return s

def setup_logger(logger_name, log_file, level=logging.INFO):
    '''Setup the analyzer logger.

    NOTE: All analyzers share the same logger.

    :param logger_name: logger to be setup.
    :param log_file: the file to save the log.
    :param level: the loggoing level. The default value is logging.INFO.
    '''

    l = logging.getLogger(logger_name)
    if len(l.handlers)<1:
        formatter = MyFormatter('%(asctime)s %(message)s',datefmt='%Y-%m-%d,%H:%M:%S.%f')
        streamHandler = logging.StreamHandler()
        streamHandler.setFormatter(formatter)

        l.setLevel(level)
        l.addHandler(streamHandler)
        l.propagate = False

        if log_file!="":
            fileHandler = logging.FileHandler(log_file, mode='w')
            fileHandler.setFormatter(formatter)
            l.addHandler(fileHandler)  
        l.disabled = False    

class Analyzer(Element):
    """A base class for all the analyzers
    """

    #Guanratee global uniqueness of analyzer
    __analyzer_array={}    #Analyzer name --> object address
    logger=None

    def __init__(self):
        Element.__init__(self)
        self.source=None    #trace source collector
        #callback when source pushes messages
        #FIXME: looks redundant with the from_list
        self.source_callback=[]    

        #setup the logs
        self.set_log("",logging.INFO)

        #Include itself into the global list
        if not self.__class__.__name__ in Analyzer.__analyzer_array:
            Analyzer.__analyzer_array[self.__class__.__name__]=self
        else:
            self.log_info("Warning: duplicate analyzer declaration: "+self.__class__.__name__)

        self.__parent_analyzer=[] #a list of analyzers it depends on

        #TODO: For Profile, each specific analyzer should declare it on demand

    #logging functions: please use this one
    def log_info(self, msg):
        Analyzer.logger.info(
            "\033[32m\033[1m[INFO]\033[0m\033[0m\033[1m["
            + self.__class__.__name__+']\033[0m: '+msg
            )

    def log_debug(self, msg):
    
        Analyzer.logger.debug(
            "\033[33m\033[1m[DEBUG]\033[0m\033[0m\033[1m["
            + self.__class__.__name__+']\033[0m: '+msg)

    def log_warning(self, msg):
        Analyzer.logger.warning(
            "\033[1;34m\033[1m[WARNING]\033[0m\033[0m\033[1m["
            + self.__class__.__name__+']\033[0m: '+msg)

    def log_error(self, msg):
        Analyzer.logger.error(
            "\033[31m\033[1m[ERROR]\033[0m\033[0m\033[1m["
            + self.__class__.__name__+']\033[0m: '+msg)

    def log_critical(self, msg):
        Analyzer.logger.critical(
            "\033[31m\033[1m[CRITICAL]\033[0m\033[0m\033[1m["
            + self.__class__.__name__+']\033[0m: '+msg)

    @staticmethod
    def reset():
        """
        Clean up all the analyzers
        """
        Analyzer.__analyzer_array={}

    def set_log(self,logpath,loglevel=logging.INFO):
        """
        Set the logging in analyzers.
        All the analyzers share the same logger.

        :param logpath: the file path to save the log
        :param loglevel: the level of the log. The default value is logging.INFO.
        """
        self.__logpath=logpath
        self.__loglevel=loglevel
        setup_logger('mobileinsight_logger',self.__logpath,self.__loglevel)
        # self.logger=logging.getLogger('mobileinsight_logger')
        Analyzer.logger=logging.getLogger('mobileinsight_logger')
  
    def set_source(self,source):
        """
        Set the source of the trace. 
        The messages from the source will drive the analysis.

        :param source: the source trace collector
        :param type: trace collector
        """

        #Bottom-up setting: the included analyzers should be evaluated first, then top analyzer

        #Recursion for analyzers it depends on
        for analyzer in self.from_list:
            analyzer.set_source(source)
            
        if self.source != None:
            self.source.deregister(self)
        self.source = source
        source.register(self)

    def add_source_callback(self,callback):
        """
        Add a callback function to the analyzer. 
        When a message arrives, the analyzer will trigger the callbacks for analysis. 

        :param callback: the callback function to be added
        """
        if callback not in self.source_callback:
            self.source_callback.append(callback)

    def rm_source_callback(self,callback):
        """
        Delete a callback function to the analyzer. 

        :param callback: the callback function to be deleted
        """
        if callback in self.source_callback:
            self.source_callback.remove(callback)

    def __get_module_name(self, analyzer_name):
        """
        Given analyzer name (local), create corresponding module name

        :param analyzer_name: the local analyzer name
        :type analyzer_name: string
        """    
        res=""
        for i in analyzer_name:
            if i.isupper():
                if res:
                    res=res+"_"+i.lower()
                else:
                    res=res+i.lower()
            else:
                res=res+i
        return res

    def include_analyzer(self,analyzer_name,callback_list,*args):
        """
        Declares the dependency from other analyzers.
        Once declared, the current analyzer will receive events 
        from other analyzers, then trigger functions in callback_list

        :param analyzer_name: the name of analyzer to depend on
        :type analyzer_name: string
        :param callback_list: a list of callback functions. They will be triggered when an event from analyzer arrives
        :param args: optional parameters for the analyzer to be included

        """
        if analyzer_name in Analyzer.__analyzer_array:
            #Analyzer has been declared. Reuse it directly
            self.from_list[Analyzer.__analyzer_array[analyzer_name]] = callback_list
            if self not in Analyzer.__analyzer_array[analyzer_name].to_list:
                Analyzer.__analyzer_array[analyzer_name].to_list.append(self)
            self.__parent_analyzer.append(analyzer_name)
        else:
            try:
                #If it's built-in analyzer, import from mobile_insight.analyzer
                module_tmp = __import__("mobile_insight.analyzer")
                analyzer_tmp = getattr(module_tmp.analyzer,analyzer_name)
                Analyzer.__analyzer_array[analyzer_name] = analyzer_tmp(*args) 
                self.from_list[Analyzer.__analyzer_array[analyzer_name]] = callback_list
                if self not in Analyzer.__analyzer_array[analyzer_name].to_list:
                    Analyzer.__analyzer_array[analyzer_name].to_list.append(self)
                self.__parent_analyzer.append(analyzer_name)
            except Exception, e:
                #Not a built-in analyzer. Try to import it from local directory
                try:
                    module_name = self.__get_module_name(analyzer_name)
                    module_tmp = __import__(module_name)
                    analyzer_tmp = getattr(module_tmp,analyzer_name)
                    Analyzer.__analyzer_array[analyzer_name] = analyzer_tmp(*args) 
                    self.from_list[Analyzer.__analyzer_array[analyzer_name]] = callback_list
                    if self not in Analyzer.__analyzer_array[analyzer_name].to_list:
                        Analyzer.__analyzer_array[analyzer_name].to_list.append(self)
                    self.__parent_analyzer.append(analyzer_name)
                except Exception, e:
                    #Either the analyzer is unavailable, or has semantic errors
                    self.logger.info("Runtime Error: unable to import "+analyzer_name)  
                    import traceback
                    import sys
                    sys.exit(str(traceback.format_exc()))

    def exclude_analyzer(self,analyzer_name):
        #TODO: this API would be depreciated
        """
        Remove the dependency from the ananlyzer

        :param analyzer: the analyzer to not depend on
        :type analyzer: string
        """

        if analyzer_name in Analyzer.__analyzer_array \
        and self in Analyzer.__analyzer_array:
            del self.from_list[Analyzer.__analyzer_array[analyzer_name]]
            Analyzer.__analyzer_array[analyzer_name].to_list.remove(self)
            analyzer.to_list.remove(self) 

            self.__parent_analyzer.remove(analyzer_name)

    def get_analyzer(self, analyzer_name):
        """
        Get the instance of an analyzer from the global repository.
        This API is useful if query for this analyzer is needed.

        :param analyzer: the analyzer to not depend on
        :type analyzer: string
        :returns: the instance of the specificed analyzer, or None if it does not exist
        """
        if analyzer_name in Analyzer.__analyzer_array \
        and analyzer_name in self.__parent_analyzer:
            return Analyzer.__analyzer_array[analyzer_name]
        else:
            return None

    def recv(self,module,event):
        """
        Handle the received events.
        This is an overload member from Element

        :param module: the analyzer/trace collector who raise the event
        :param event: the event to be raised
        """
        
        # A lambda function: input as a callback, output as passing event to this callback
        G = lambda f: f(event) 

        if module==self.source:
            #Apply the event to all source callbacks
            map(G,self.source_callback)
        else:
            map(G,self.from_list[module])
