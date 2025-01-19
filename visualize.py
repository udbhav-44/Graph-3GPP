from DataModel.datamodel import DataModel
import sys
sys.path.append('/git_folder/udbhav/code/Graph-3GPP/DataModel')
import erdantic as erd

erd1 = erd.create(DataModel)
#save the diagram
erd1.draw("erd.png")