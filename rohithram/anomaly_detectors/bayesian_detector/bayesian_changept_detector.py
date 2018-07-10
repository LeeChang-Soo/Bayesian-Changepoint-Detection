

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# importing modules to run the algo
import bayesian_changepoint_detection.online_changepoint_detection as oncd
from functools import partial
import matplotlib.cm as cm

class Bayesian_Changept_Detector():
    def __init__(self,data,assetno,is_train=False,data_col_index=0,pthres=0.5,mean_runlen = 100,Nw=10,to_plot=True):
        
        '''
        Class which is used to find Changepoints in the dataset with given algorithm parameters.
        It has all methods related to finding anomalies to plotting those anomalies and returns the
        data being analysed and anomaly indexes.
        Arguments :
        data -> dataframe which has one or two more metric columnwise
        assetno -> assetno of the dataset
        is_train -> By Default is False , as no training required for this algo
        data_col_index -> column index of the metric to find changepoints on
        pthres -> Default value :0.5 , (float) it is threshold after which a changepoint is flagged as on anomaly
        mean_runlen -> (int) By default 100, It is the average gap between two changepoints , this comes from 
                       nitty gritty math of exponential distributions
        Nw (samples to wait) -> (int) By default 10 is being used for optimal performance. It is the samples after which
                                we start assigning probailities for it to be a changepoint.
        to_plot -> True if you want to plot anomalies
        '''
        
        
        self.algo_name = 'bayesian_change_point_detection'
        self.algo_code = 'bcp'
        self.algo_type = 'univariate'
        self.istrainable = is_train
        self.data = data
        self.data_col_index = data_col_index
        self.metric_name = data.columns[data_col_index]
        self.assetno = assetno
        self.pthres = pthres
        self.mean_runlen = mean_runlen
        self.Nw = Nw
        self.to_plot = to_plot


    def detect_anomalies(self):
        
        '''
        Detects anomalies and returns data and anomaly indexes
        '''
        data = self.data
        print("Shape of the dataset : ")
        print(data.shape)

        ncol = self.data_col_index

        R,maxes = self.findonchangepoint(data[data.columns[ncol]].values)
        anom_indexes = self.findanomindexes(R,maxes)
        self.anom_indexes = anom_indexes
        print("\n No of Anomalies detected = %g"%(len(anom_indexes)))

        return data,anom_indexes
    
    
    def findonchangepoint(self,data):
        '''
        finds the changepoints and returns the run lenth probability matrix and indexes of maximum run lengths
        probability
        '''
        R, maxes = oncd.online_changepoint_detection(data, partial(oncd.constant_hazard,self.mean_runlen),
                                                     oncd.StudentT(0.1, .01, 1, 0))
        return R,maxes
    

    def findthreshold(self,data):
        
        '''
        finds inversion points where probability is greater than mean
        Returns -> list of inversion points
        '''
        mu = np.mean(data)
        inv_pt = []
        for i in range(len(data)-1):
            if((data[i+1]>mu and data[i]<=mu) or (data[i+1]<mu and data[i]>=mu)):
                inv_pt.append(i)

        return inv_pt    
    
    
    def findanomindexes(self,R,maxes):
        '''
        Function to find the anomaly indexes (changepoint locations)
        Arguments: 
        R -> numpy 2D array, Run length probability matrix
        maxes -> numpy array, Run length which has maximum probability  for each possible datapoint
        
        Returns:
        anom_indexes -> anomaly indexes (list of indices)
        '''
        Nw = self.Nw
        data = self.data
        pthres = self.pthres
        
        # This code logic is referred from the github, I couldn't figure out the reason for this.
        # This is the probabilities for each datapoint to be a changepoint
        cp_probs = np.array(R[Nw,Nw:-1][1:-2])
        
        #Finds the list of locations where the left of it is less than mean probability, and right of it is more
        inversion_pts = self.findthreshold(cp_probs)
        
        #Finding indexes of maximum probability among window of points between two inversion points
        # This is done to get maximum probability among a anomalous region above the mean probability
        
        max_indexes = [inversion_pts[i]+np.argmax(cp_probs[inversion_pts[i]:inversion_pts[i+1]+1]) 
                       for i in range(len(inversion_pts)-1)]
            
        cp_mapped_probs = pd.Series(cp_probs[max_indexes],index=max_indexes)
        anom_indexes = cp_mapped_probs.index[(np.where(cp_mapped_probs.values>pthres)[0])]
        
        if(self.to_plot):
            self.plotonchangepoints(anom_indexes=anom_indexes,cp_probs=cp_probs)
            
        return anom_indexes
    
    
    def plotonchangepoints(self,anom_indexes,cp_probs,nrow=None):
        '''
        plots the original data and anomaly indexes as vertical line
        and plots run length distribution and probability score for each possible run length
        '''
        fig,(ax1,ax3) = plt.subplots(2,figsize=[18, 16])
        ncol = self.data_col_index
        data = self.data
        pthres = self.pthres
        
        ltext = 'Column : '+str(ncol+1)+' data with threshold probab = '+ str(pthres)

        ax1.set_title(data.columns[ncol])

        if(nrow==None):
            ax1.plot(data.values[:,ncol],label=ltext)
        else:
            ax1.plot(data.values[:nrow,ncol],label=ltext)

        ax1.legend()

        [ax1.axvline(x=a,color='r') for a in anom_indexes]

        '''
        This is graph for Run Length probability distribution, its commented since it takes
        Lot of time to compute the graph
        '''
#         sparsity = 5  # only plot every fifth data for faster display
#         ax2.pcolor(np.array(range(0, len(R[:,0]), sparsity)), 
#                   np.array(range(0, len(R[:,0]), sparsity)), 
#                   -np.log(R[0:-1:sparsity, 0:-1:sparsity]), 
#                   cmap=cm.Greys, vmin=0, vmax=30,label="Distribution of Run length")
#         ax2.legend()

        ax3.plot(cp_probs)

        ax3.set_title('Change points with Probability')

        plt.show()

        return anom_indexes