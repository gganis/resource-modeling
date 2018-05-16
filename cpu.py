#! /usr/bin/env python

"""
Usage: ./cpu.py config1.json,config2.json,...,configN.json

Determine the CPU model by running under various configuration changes. BaseModel.json and RealisticModel.json
provide defaults and configN.json overrides values in those configs or earlier ones in the list
"""

from __future__ import division
from __future__ import print_function

import sys
import collections
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import json
from configure import configure, run_model, mc_event_model, in_shutdown
from performance import performance_by_year
from utils import time_dependent_value

# Basic parameters
kilo = 1000
mega = 1000 * kilo
giga = 1000 * mega
tera = 1000 * giga
peta = 1000 * tera
seconds_per_year = 86400 * 365
seconds_per_month = 86400 * 30
running_time = 7.8E06

modelNames = None
if len(sys.argv) > 1:
    modelNames=[]
    for a in sys.argv[1:]:
        modelNames = modelNames+ a.split(',')
model = configure(modelNames)

# The very important list of years
YEARS = list(range(model['start_year'], model['end_year']+1))

# Get the performance year by year which includes the software improvement factor
reco_time = {year: performance_by_year(model, year, 'RECO', data_type='data')[0] for year in YEARS}

lhc_sim_time = {year: performance_by_year(model, year, 'GENSIM',
                                              data_type='mc', kind='2017')[0] +
                  performance_by_year(model, year, 'DIGI',
                                          data_type='mc', kind='2017')[0] +
                  performance_by_year(model, year, 'RECO',
                                          data_type='mc', kind='2017')[0] for year in YEARS}

hllhc_sim_time = {year: performance_by_year(model, year, 'GENSIM',
                                            data_type='mc', kind='2026')[0] +
                        performance_by_year(model, year, 'DIGI',
                                            data_type='mc', kind='2026')[0] +
                        performance_by_year(model, year, 'RECO',
                                            data_type='mc', kind='2026')[0] for year in YEARS}

print("Year / Reco / LHC SIM / HLLHC SIM times")
for year in YEARS:
    print(year,int(reco_time[year]),int(lhc_sim_time[year]),int(hllhc_sim_time[year]))
print()

# general pattern:
# _required: HS06
# _time: HS06s

# CPU time requirement calculations, in HS06 * s
# Take the running time and event rate from the model

data_events = {i: run_model(model, i, data_type='data').events for i in YEARS}
lhc_mc_events = {i: mc_event_model(model, i)['2017']  for i in YEARS}
hllhc_mc_events = {i: mc_event_model(model, i)['2026']  for i in YEARS}

cpu_efficiency = model['cpu_efficiency']

#Note the quantity below is for prompt reco only.
data_cpu_time = {i : data_events[i] * reco_time[i] / cpu_efficiency for i in YEARS}
lhc_mc_cpu_time = {i : lhc_mc_events[i] * lhc_sim_time[i] / cpu_efficiency for i in YEARS}
hllhc_mc_cpu_time = {i : hllhc_mc_events[i] * hllhc_sim_time[i] / cpu_efficiency for i in YEARS}

# The data need to be reconstructed about as quickly as we record them.  In
# addition, we need to factor in express, repacking, AlCa, CAF
# functionality and skimming.  Presumably these all scale like the data.
# Per the latest CRSG document, these total to 123 kHS06 compared to 240
# kHS016 for the prompt reconstruction, which we can round to 50%, so
# multiply by 50%.  (Ignoring the 10 kHS06 needed for VO boxes, which
# won't scale up and is also pretty small.)

data_cpu_required = {i : (1.5 * data_cpu_time[i] / running_time)
                         for i in YEARS}

# Also keep using the _time variables to sum up the total HS06 * s needed,
# which frees us from assumptions on time needed to complete the work.

data_cpu_time = {i : 1.5 * data_cpu_time[i] for i in YEARS}

# In-year reprocessing model: assume we will re-reco 25% of the data each
# year, but we want to complete it in one month.  We also re-reco 25% of
# the previous year's data (assumed to be the same number of events as this
# year) but we want to do that in three months.

rereco_cpu_required = {i : (1.0/ cpu_efficiency)*max(0.25 * data_events[i] * reco_time[i]/ seconds_per_month,
                                                     data_events[i] * reco_time[i] / (3 * seconds_per_month))
                         for i in YEARS}

# But the total time needed is the sum of both activities.

rereco_cpu_time = {i : (1.25 * data_events[i] * reco_time[i]) for i in YEARS}
    

# The corresponding MC, on the other hand, can be reconstructed over an
# entire year.  We can use this to calculate the HS06 needed to do those
# tasks.

lhc_mc_cpu_required = {i : lhc_mc_cpu_time[i] / seconds_per_year for i in YEARS}
hllhc_mc_cpu_required = {i : hllhc_mc_cpu_time[i] / seconds_per_year for i in YEARS}

# Unless it is a year with new detectors in, in which case we will have
# less time to make MC (say half as much).  Only applies to the current
# era, i.e. no need to compress HL-LHC MC when we are still in LHC era.

for i in YEARS:
    if (i in model['new_detector_years']):
        if i < 2026:
            lhc_mc_cpu_required[i] = lhc_mc_cpu_time[i]/ (seconds_per_year / 2)
        else:
            hllhc_mc_cpu_required[i] = hllhc_mc_cpu_time[i]/ (seconds_per_year / 2)
            

# Analysis!  Following something like the 2018 resource request, we make this
# 75% of everything else (for a moment).

# new json driven model
# conconstant time to read - just driven by analysis sets

if 'AnalysisSet' in model:
    print("Using new analysis method")

    
    analysis_cpu_time={}
    for i in YEARS:
        dataReads,ty = time_dependent_value(year=i,values=model['AnalysisReadsPerYearData'])
        mcReads,ty = time_dependent_value(year=i,values=model['AnalysisReadsPerYearMC'])
        analysis_cpu_time[i]=0.
        for j in model['AnalysisSet'][str(i)]:
            # 2.25 is 1 for prompt + 1.25 of rereco
            analysis_cpu_time[i] += model['AnalysisCPUPerEvent'] * dataReads*2.25*data_events[j]
            analysis_cpu_time[i] += model['AnalysisCPUPerEvent'] * mcReads*lhc_mc_events[j]
        if i > 2025:
            for j in model['AnalysisSet'][str(i)]:
                analysis_cpu_time[i] += model['AnalysisCPUPerEvent'] * mcReads*hllhc_mc_events[j]
        else:
            analysis_cpu_time[i] += model['AnalysisCPUPerEvent'] * mcReads*hllhc_mc_events[i]
        analysis_cpu_time[i] = analysis_cpu_time[i]  / cpu_efficiency

    analysis_cpu_required={}

    # allow a component that scales with reconstruction
    analysisScaledByReco = model['AnalysisCPUScaledByReco']
    if analysisScaledByReco > 0:
        for i in YEARS:
            analysis_cpu_time[i] += analysisScaledByReco * (lhc_mc_cpu_time[i] + hllhc_mc_cpu_time[i] + 
                                                            data_cpu_time[i] +  rereco_cpu_time[i])
    #now sum up everything
    for i in YEARS:
        analysis_cpu_required[i] = analysis_cpu_time[i]/seconds_per_year

else:
    print("Using old analysis method")

    analysis_cpu_required = {i : 0.75 *
                             (lhc_mc_cpu_required[i] + hllhc_mc_cpu_required[i] +
                              data_cpu_required[i] + rereco_cpu_required[i])
                             for i in YEARS}
    
    analysis_cpu_time = {i : 0.75* (data_cpu_time[i] + rereco_cpu_time[i] +
                         lhc_mc_cpu_time[i] + hllhc_mc_cpu_time[i])
                         for i in YEARS}

# But do something a little funkier for the time up to HL-LHC.  We are
# accumulating data, so analysis should keep taking longer.  Assume 2018 is
# "right".  In 2019 we will analyze 2018 data in addition to 2016 and 2017,
# so make 2019 1/3 bigger.  Keep the same amount through the shutdown when
# we don't accumulate data.  Then after the shutdown we keep adding in data
# years that are the same size as the previous ones, and then keep that
# flat until we ramp up HL-LHC studies in 2025 and we revert back to the
# 75% model.  Implemented here as a complete kludge.  Note that by kludging
# this way we don't absorb the software improvement factors...but that's
# OK, the analysis is I/O bound anyway and doesn't benefit from such
# improvements.

    analysis_cpu_time[2019] = (4/3) * analysis_cpu_time[2018]
    analysis_cpu_time[2020] = analysis_cpu_time[2019]
    analysis_cpu_time[2021] = analysis_cpu_time[2019]
    analysis_cpu_time[2022] = (5/4)* analysis_cpu_time[2021]
    analysis_cpu_time[2023] = (6/5)* analysis_cpu_time[2022]
    analysis_cpu_time[2024] = (7/6)* analysis_cpu_time[2023]
    
# More kludging: assume analysis takes place all year to calculate the HS06
# required for the above analysis CPU time.  Eric will hate this, I do too,
# we should fix it up later.

    for i in YEARS:
        if (i >= 2019 and i < 2025):
            analysis_cpu_required[i] = analysis_cpu_time[i]/seconds_per_year

# Shutdown year model:

# If in the first year of a shutdown, need to reconstruct the previous
# three years of data, but you have all year to do it.  No need for all the
# ancillary stuff.  We need to do the MC also...assume similarly that we
# have three times as many events as we had the previous year.

date_rereco_two_years=model['first_year_to_spread_rereco_over_two_years']
for i in YEARS:
    shutdown_this_year, dummy = in_shutdown(model,i)
    shutdown_last_year, dummy = in_shutdown(model,i-1)
    shutdown_next_year, dummy = in_shutdown(model,i+1)
    if (shutdown_this_year and not(shutdown_last_year)):
        data_events[i] = 3 * data_events[i-1]
        if i >=date_rereco_two_years:
            data_events[i]=0.5*data_events[i]
        rereco_cpu_time[i] = data_events[i] * reco_time[i] / cpu_efficiency
        rereco_cpu_required[i] = rereco_cpu_time[i] / seconds_per_year

        if i >=date_rereco_two_years:
            if i+1 in data_events:
                if shutdown_next_year:
                    data_events[i+1]=0
                    rereco_cpu_time[i+1]=0
                    rereco_cpu_required[i+1]=0
                data_events[i+1]+=data_events[i]
                rereco_cpu_time[i+1] += rereco_cpu_time[i]
                rereco_cpu_required[i+1] += rereco_cpu_required[i]

        if i < 2025:
            lhc_mc_events[i] = 3 * lhc_mc_events[i-1]
            if i >=date_rereco_two_years:
                lhc_mc_events[i]= 0.5*lhc_mc_events[i]
            lhc_mc_cpu_time[i] = lhc_mc_events[i] * lhc_sim_time[i] / cpu_efficiency
            lhc_mc_cpu_required[i] = lhc_mc_cpu_time[i] / seconds_per_year
            if i >=date_rereco_two_years:
                if i+1 in lhc_mc_events:
                    if shutdown_next_year:
                        lhc_mc_events[i+1]=0
                        lhc_mc_cpu_time[i+1]=0
                        lhc_mc_cpu_required[i+1]=0
                    lhc_mc_events[i+1] += lhc_mc_events[i]
                    lhc_mc_cpu_time[i+1] += lhc_mc_cpu_time[i]
                    lhc_mc_cpu_required[i] += lhc_mc_cpu_required[i]
                    

        else:
            hllhc_mc_events[i] = 3 * hllhc_mc_events[i-1]
            if i >=date_rereco_two_years:
                hllhc_mc_events[i]=0.5*hllhc_mc_events[i]

            hllhc_mc_cpu_time[i] = hllhc_mc_events[i] * hllhc_sim_time[i] / cpu_efficiency
            hllhc_mc_cpu_required[i] = hllhc_mc_cpu_time[i] / seconds_per_year
            if i >=date_rereco_two_years:
                if i+1 in hllhc_mc_events:
                    if shutdown_next_year:
                        hllhc_mc_events[i+1]=0
                        hllhc_mc_cpu_time[i+1]=0
                        hllhc_mc_cpu_required[i+1]=0
                    hllhc_mc_events[i+1] += hllhc_mc_events[i]
                    hllhc_mc_cpu_time[i+1] += hllhc_mc_cpu_time[i]
                    hllhc_mc_cpu_required[i+1] += hllhc_mc_cpu_required[i]

# Sum up everything

total_cpu_required = {i : data_cpu_required[i] + rereco_cpu_required[i] +
                          lhc_mc_cpu_required[i] +
                          hllhc_mc_cpu_required[i] +
                          analysis_cpu_required[i] for i in YEARS}

total_cpu_time = {i: data_cpu_time[i] + rereco_cpu_time[i] +
                      lhc_mc_cpu_time[i] +
                      hllhc_mc_cpu_time[i] + analysis_cpu_time[i]
                      for i in YEARS}

hpc_cpu_required = {i : rereco_cpu_required[i] +
                          lhc_mc_cpu_required[i] +
                          hllhc_mc_cpu_required[i] for i in YEARS}

hpc_cpu_time = {i: rereco_cpu_time[i] +
                      lhc_mc_cpu_time[i] +
                      hllhc_mc_cpu_time[i] for i in YEARS}

# Then, CPU availability calculations.  This follows the "Available CPU
# power" spreadsheet.  Take a baseline value of 1.4 MHS06 in 2016, in
# future years subtract 5% of the previous for retirements, and add 300
# kHS06 which gets improved by the cpu_improvement in each year, until
# 2020, during LS2, when we shift the computing model to start buying an
# improved 600 kHS06 per year.

# This is kludgey -- need to establish the baseline to make the
# caluculation work, but once the calculation is there, delete the baseline
# for the histogram to work.  Not to mention that I couldn't get the
# dictionary comprehension to work here.

cpu_improvement_factor = model['improvement_factors']['hardware']
cpu_improvement = {i : cpu_improvement_factor ** (i-2017) for i in YEARS}

#YUCK - I don't know how to get around this hardwired thingy
cpu_capacity = {YEARS[0]-1 : 1.4 * mega}

# This variable assumes that you can have the cpu_capacity for an entire
# year and thus calculates the HS06 * s available (in principle).

cpu_time_capacity = {YEARS[0]-1 : 1.4 * mega}

retirement_rate = 0.05

for i in YEARS:
    cpu_capacity[i] = cpu_capacity[i-1] * (1 - retirement_rate) + (300 if i < 2020 else 600) * kilo * cpu_improvement[i]
    cpu_time_capacity[i] = cpu_capacity[i] * seconds_per_year

del cpu_capacity[YEARS[0]-1]
del cpu_time_capacity[YEARS[0]-1]

# CPU capacity model ala data.py

# Set the initial points
cpuCapacity = {str(model['capacity_model']['cpu_year']): model['capacity_model']['cpu_start']}
cpuTimeCapacity = {str(model['capacity_model']['cpu_year']): model['capacity_model']['cpu_start'] * seconds_per_year}


# A bit of a kludge. Assume what we have now was bought and will be retired in equal chunks over its lifetime
cpuAdded = {}
for year in range(model['capacity_model']['cpu_year'] - model['capacity_model']['cpu_lifetime'] + 1,
                  model['capacity_model']['cpu_year'] + 1):
    retired = model['capacity_model']['cpu_start'] / model['capacity_model']['cpu_lifetime']
    cpuAdded[str(year)] = retired

cpuFactor = model['improvement_factors']['hardware']

for year in YEARS:
    if str(year) not in cpuCapacity:
        cpuDelta = 0  # Find the delta which can be time dependant
        cpuDeltas = model['capacity_model']['cpu_delta']
        for deltaYear in sorted(cpuDeltas.keys()):
            if int(year) >= int(deltaYear):
                lastCpuYear = int(deltaYear)
                cpuDelta = model['capacity_model']['cpu_delta'][deltaYear]

        cpuAdded[str(year)] = cpuDelta * cpuFactor ** (int(year) - int(lastCpuYear))

        # Retire cpu added N years ago or retire 0

        cpuRetired = cpuAdded.get(str(int(year) - model['capacity_model']['cpu_lifetime']), 0)
        cpuCapacity[str(year)] = cpuCapacity[str(int(year) - 1)] + cpuAdded[str(year)] - cpuRetired
        cpuTimeCapacity[str(year)] = cpuCapacity[str(year)] * seconds_per_year 

print("CPU requirements in HS06")
print("Year Prompt NonPrompt LHCMC HLLHCMC Ana Total Cap1 Cap2 Ratio USCMS HPC")
for i in YEARS:
    print(i, '{:04.3f}'.format(data_cpu_required[i] / mega),
    '{:04.3f}'.format(rereco_cpu_required[i] / mega),
    '{:04.3f}'.format(lhc_mc_cpu_required[i] / mega),
    '{:04.3f}'.format(hllhc_mc_cpu_required[i] / mega),
    '{:04.3f}'.format(analysis_cpu_required[i] / mega),
    '{:04.3f}'.format(total_cpu_required[i] / mega),
    '{:04.3f}'.format(cpu_capacity[i] / mega),
    '{:04.3f}'.format(cpuCapacity[str(i)] / mega), 'MHS06',
    '{:04.3f}'.format(total_cpu_required[i]/cpuCapacity[str(i)]),
    '{:04.3f}'.format(0.4* (total_cpu_required[i]) / mega),
    '{:04.3f}'.format(hpc_cpu_required[i]/total_cpu_required[i])
              )

print("CPU requirements in HS06 * s")
print("Year Prompt NonPrompt LHCMC HLLHCMC Ana Total Cap1 Cap2 Ratio USCMS HPC")
for i in YEARS:
    print(i, '{:03.2f}'.format(data_cpu_time[i] / tera),
    '{:03.2f}'.format(rereco_cpu_time[i] / tera),
    '{:03.2f}'.format(lhc_mc_cpu_time[i] / tera),
    '{:03.2f}'.format(hllhc_mc_cpu_time[i] / tera),
    '{:03.2f}'.format(analysis_cpu_time[i] / tera),
    '{:03.2f}'.format(total_cpu_time[i] / tera),
    '{:03.2f}'.format(cpu_time_capacity[i] / tera),
    '{:03.2f}'.format(cpuTimeCapacity[str(i)] / tera), 'THS06 * s',
    '{:03.2f}'.format(total_cpu_time[i] / cpuTimeCapacity[str(i)]),
    '{:03.2f}'.format(0.4* (total_cpu_time[i]) / tera),
    '{:03.2f}'.format(hpc_cpu_time[i]/total_cpu_time[i])
              )


print("Fraction of CPU required for T1/T2 activities")
print("Year\t Prmpt\t Rreco\tGen\tSim\tSimReco\t Anal\t USCPU")

genFractionOfTotal=0.03
us_fraction=model['us_fraction_T1T2']


for i in YEARS:
    #first some calculations we didn't do before
    lhcSim=performance_by_year(model, year, 'GENSIM', data_type='mc', kind='2017')[0]
    lhcDigi=performance_by_year(model, year, 'DIGI', data_type='mc', kind='2017')[0]
    lhcReco=performance_by_year(model, year, 'RECO', data_type='mc', kind='2017')[0]
    hllhcSim=performance_by_year(model, year, 'GENSIM', data_type='mc', kind='2026')[0]
    hllhcDigi=performance_by_year(model, year, 'DIGI', data_type='mc', kind='2026')[0]
    hllhcReco=performance_by_year(model, year, 'RECO', data_type='mc', kind='2026')[0]

    lhcDigiFraction=lhcDigi/(lhcSim+lhcDigi+lhcReco)
    lhcRecoFraction=lhcReco/(lhcSim+lhcDigi+lhcReco)
    lhcSimFraction=lhcSim/(lhcSim+lhcDigi+lhcReco)

    hllhcDigiFraction=hllhcDigi/(hllhcSim+hllhcDigi+hllhcReco)
    hllhcRecoFraction=hllhcReco/(hllhcSim+hllhcDigi+hllhcReco)
    hllhcSimFraction=hllhcSim/(hllhcSim+hllhcDigi+hllhcReco)

    lhcFraction= lhc_mc_cpu_time[i] / (lhc_mc_cpu_time[i] + hllhc_mc_cpu_time[i])

    totalT1T2 = (total_cpu_time[i] - data_cpu_time[i])*(1.0+genFractionOfTotal)
    
    totGenFraction = genFractionOfTotal
    totSimFraction = (lhcSimFraction*lhcFraction + hllhcSimFraction*(1.0-lhcFraction))*(lhc_mc_cpu_time[i] + hllhc_mc_cpu_time[i]) / totalT1T2
    totDigiFraction = (lhcDigiFraction*lhcFraction + hllhcDigiFraction*(1.0-lhcFraction))*(lhc_mc_cpu_time[i] + hllhc_mc_cpu_time[i]) / totalT1T2
    totRecoFraction = (lhcRecoFraction*lhcFraction + hllhcRecoFraction*(1.0-lhcFraction))*(lhc_mc_cpu_time[i] + hllhc_mc_cpu_time[i]) / totalT1T2

    rerecoFraction = rereco_cpu_time[i] / totalT1T2
    analysisFraction = analysis_cpu_time[i] / totalT1T2
    promptFraction = 0.
    uscpu= totalT1T2*us_fraction/tera

    print(i,'\t',
    '{:04.3f}'.format(promptFraction),'\t',
    '{:04.3f}'.format(rerecoFraction),'\t',
    '{:04.3f}'.format(totGenFraction),'\t',
    '{:04.3f}'.format(totSimFraction),'\t',
    '{:04.3f}'.format(totDigiFraction+totRecoFraction),'\t',
    '{:04.3f}'.format(analysisFraction),'\t',
    '{:04.2f}'.format(uscpu),'\t'
    )


# Plot the HS06

# Squirt the dictionary entries into lists:

cpuDataList = []
for year, item in sorted(data_cpu_required.items()):
    cpuDataList.append(item/mega)
cpuRerecoList = []
for year, item in sorted(rereco_cpu_required.items()):
    cpuRerecoList.append(item/mega)
cpuLHCMCList = []
for year, item in sorted(lhc_mc_cpu_required.items()):
    cpuLHCMCList.append(item/mega)
cpuHLLHCMCList = []
for year, item in sorted(hllhc_mc_cpu_required.items()):
    cpuHLLHCMCList.append(item/mega)
cpuAnaList = []
for year, item in sorted(analysis_cpu_required.items()):
    cpuAnaList.append(item/mega)
cpuCapacityList = []
for year, item in sorted(cpu_capacity.items()):
    cpuCapacityList.append(item/mega)
altCapacityList = []
print (cpu_capacity)
print (cpuCapacity)
for year, item in sorted(cpuCapacity.items()):
    if int(year) in cpu_capacity:
        altCapacityList.append(item/mega)

# Build a data frame from lists:

pngKeyName=''
if modelNames is not None:
    for m in modelNames:
        pngKeyName=pngKeyName+'_'+m.split('/')[-1].split('.')[0]


plotMaxs=model['plotMaximums']

cpuFrame = pd.DataFrame({'Year': [str(year) for year in YEARS],
                             'Prompt Data' : cpuDataList,
                             'Non-Prompt Data' : cpuRerecoList,
                             'LHC MC' : cpuLHCMCList,
                             'HL-LHC MC' : cpuHLLHCMCList,
                             'Analysis' : cpuAnaList}
                            )


ax = cpuFrame[['Year', 'Prompt Data', 'Non-Prompt Data', 'LHC MC', 'HL-LHC MC',
                   'Analysis']].plot(x='Year',kind='bar',stacked=True,colormap='Paired')
ax.set(ylabel='MHS06')
ax.set(title='CPU by Type')

handles, labels = ax.get_legend_handles_labels()
handles=handles[::-1]
labels=labels[::-1]
ax.legend(handles,labels,loc='best', markerscale=0.25, fontsize=11)
ax.set_ylim(ymax=plotMaxs['CPUByType'])
minYearVal=max(0,model['minYearToPlot']-YEARS[0])-0.5 #pandas...

ax.set_xlim(xmin=minYearVal)
fig = ax.get_figure()
fig.tight_layout()
fig.savefig('CPUByType'+pngKeyName+'.png') 

cpuCapacityFrame = pd.DataFrame({'Year': [str(year) for year in YEARS],
                             'Prompt Data' : cpuDataList,
                             'Non-Prompt Data' : cpuRerecoList,
                             'LHC MC' : cpuLHCMCList,
                             'HL-LHC MC' : cpuHLLHCMCList,
                             'Analysis' : cpuAnaList,
                             'Capacity, 5% retirement' : cpuCapacityList,
                             'Capacity, 5 year retirement' : altCapacityList}
                            )


ax = cpuCapacityFrame[['Year','Capacity, 5% retirement']].plot(x='Year',linestyle='-',marker='o', color='Red')
cpuCapacityFrame[['Year','Capacity, 5 year retirement']].plot(x='Year',linestyle='-',marker='o', color='Blue',ax=ax)
cpuCapacityFrame[['Year', 'Prompt Data', 'Non-Prompt Data', 'LHC MC',
                      'HL-LHC MC', 'Analysis']].plot(x='Year',kind='bar',stacked=True,ax=ax,colormap='Paired')
ax.set(ylabel='MHS06')
ax.set(title='CPU by Type and Capacity')
ax.set_ylim(ymax=plotMaxs['CPUByTypeAndCapacity'])
ax.set_xlim(xmin=minYearVal)
handles, labels = ax.get_legend_handles_labels()
handles=handles[::-1]
labels=labels[::-1]
ax.legend(handles,labels,loc='best', markerscale=0.25, fontsize=11)



fig = ax.get_figure()
fig.tight_layout()
fig.savefig('CPUByTypeAndCapacity'+pngKeyName+'.png')

# Do the same thing for the HS06 * d

# Squirt the dictionary entries into lists:

cpuDataTimeList = []
for year, item in sorted(data_cpu_time.items()):
    cpuDataTimeList.append(item/tera)
cpuRerecoTimeList = []
for year, item in sorted(rereco_cpu_time.items()):
    cpuRerecoTimeList.append(item/tera)
cpuLHCMCTimeList = []
for year, item in sorted(lhc_mc_cpu_time.items()):
    cpuLHCMCTimeList.append(item/tera)
cpuHLLHCMCTimeList = []
for year, item in sorted(hllhc_mc_cpu_time.items()):
    cpuHLLHCMCTimeList.append(item/tera)
cpuAnaTimeList = []
for year, item in sorted(analysis_cpu_time.items()):
    cpuAnaTimeList.append(item/tera)
cpuCapacityTimeList = []
for year, item in sorted(cpu_time_capacity.items()):
    cpuCapacityTimeList.append(item/tera)
altCapacityTimeList = []
for year, item in sorted(cpuTimeCapacity.items()):
    if int(year) in cpu_time_capacity:
        altCapacityTimeList.append(item/tera)

# Build a data frame from lists:

cpuTimeFrame = pd.DataFrame({'Year': [str(year) for year in YEARS],
                             'Prompt Data' : cpuDataTimeList,
                             'Non-Prompt Data' : cpuRerecoTimeList,
                             'LHC MC' : cpuLHCMCTimeList,
                             'HL-LHC MC' : cpuHLLHCMCTimeList,
                             'Analysis' : cpuAnaTimeList}
                            )


ax = cpuTimeFrame[['Year', 'Prompt Data', 'Non-Prompt Data', 'LHC MC', 'HL-LHC MC', 'Analysis']].plot(x='Year',kind='bar',stacked=True,colormap='Paired')
ax.set(ylabel='THS06 * s')
ax.set(title='CPU seconds by Type')
ax.set_ylim(ymax=plotMaxs['CPUSecondsByType'])
ax.set_xlim(xmin=minYearVal)

handles, labels = ax.get_legend_handles_labels()
handles=handles[::-1]
labels=labels[::-1]
ax.legend(handles,labels,loc='best', markerscale=0.25, fontsize=11)

fig = ax.get_figure()
fig.tight_layout()
fig.savefig('CPUSecondsByType'+pngKeyName+'.png')


cpuTimeCapacityFrame = pd.DataFrame({'Year': [str(year) for year in YEARS],
                                'Prompt Data' : cpuDataTimeList,
                                'Non-Prompt Data' : cpuRerecoTimeList,
                                'LHC MC' : cpuLHCMCTimeList,
                                'HL-LHC MC' : cpuHLLHCMCTimeList,
                                'Analysis' : cpuAnaTimeList,
                                'Capacity, 5% retirement' : cpuCapacityTimeList,
                                    'Capacity, 5 year retirement' : altCapacityTimeList}
                                )


ax = cpuTimeCapacityFrame[['Year','Capacity, 5% retirement']].plot(x='Year',linestyle='-',marker='o', color='Red')
cpuTimeCapacityFrame[['Year','Capacity, 5 year retirement']].plot(x='Year',linestyle='-',marker='o', color='Blue',ax=ax)
cpuTimeCapacityFrame[['Year', 'Prompt Data', 'Non-Prompt Data', 'LHC MC', 'HL-LHC MC', 'Analysis']].plot(x='Year',kind='bar',stacked=True,ax=ax,colormap='Paired')
ax.set(ylabel='THS06 * s')
ax.set(title='CPU seconds by Type and Capacity')
ax.set_ylim(ymax=plotMaxs['CPUSecondsByTypeAndCapacity'])
ax.set_xlim(xmin=minYearVal)

handles, labels = ax.get_legend_handles_labels()
handles=handles[::-1]
labels=labels[::-1]
ax.legend(handles,labels,loc='best', markerscale=0.25, fontsize=11)

fig = ax.get_figure()
fig.tight_layout()
fig.savefig('CPUSecondsByTypeAndCapacity'+pngKeyName+'.png')


