import oracledb
import sys, os
import time
import datetime
import pytz
import numpy as np
import pandas as pd
import argparse
from utils.dbmanager import add_run_day_pot, add_run_pot, create_connection, create_table
from beaminfo.simple_query import query_pot_interval
from runinfo.read_run_info import make_timestamp, parse_line

## Arguments
parser = argparse.ArgumentParser(description='Updating Fermilab directorate performance database')
parser.add_argument('-i', dest="Start")
parser.add_argument('-f', dest="End", default="", help="If blank, will be automatically set to start_day+7days") # optional
parser.add_argument('--dev', action='store_true', help="Update develop area for test")
parser.add_argument('--prod', action='store_true', help="Update production area")
parser.add_argument('--no_commit', action='store_true')
args = parser.parse_args()

## Env
ICARUSACCOUNT = os.environ["ICARUSACCOUNT"]
ICARUSPWD = os.environ["ICARUSPWD"]

## Constants
BNB_MaximumRate = 5.0 # Hz
NuMI_MaximumRate = 1./1.4 # Hz

## flags
DoNotCommit = args.no_commit
UpdateDev = args.dev
UpdateProd = args.prod
if not UpdateDev and not UpdateProd:
  print("Either --dev or --prod should be used")
  raise
if UpdateDev and UpdateProd:
  print("--dev and --prod cannot be used at the same time")
  raise

## Start date in YYYY-MM-DD foramt, should be Monday
start_day = args.Start
end_day = args.End

datetime_start = datetime.datetime.fromisoformat(start_day)
datetime_end = datetime_start + datetime.timedelta(days=6) if end_day=="" else datetime.datetime.fromisoformat(end_day)
end_day = datetime_end.strftime("%Y-%m-%d") if end_day=="" else end_day
timeInterval = datetime_end-datetime_start+datetime.timedelta(days=1)
print("@@ Updating data quality for %s ~ %s"%(datetime_start.strftime("%Y-%m-%d %a"), datetime_end.strftime("%Y-%m-%d %a")))

potDir = os.environ["potDir"]
dbname = "%s/dbase/RunSummary.db"%(potDir)
conn = create_connection(dbname)

pot_run_collected = pd.read_sql( "SELECT * from daily_collected_pot", conn )
pot_daily_bnb = pd.read_sql( "SELECT day, pot, spill, mode FROM day_pot_bnb", conn )
pot_daily_numi = pd.read_sql( "SELECT day, pot, spill, mode FROM day_pot_numi", conn )

conn.close()

# Merge BNB
pot_run_collected = pot_run_collected.join( pot_daily_bnb.set_index("day"), on="day" )
pot_run_collected.rename( columns={ "pot" : "pot_bnb_delivered"}, inplace=True )
pot_run_collected.rename( columns={ "spill" : "spill_bnb_delivered"}, inplace=True )
pot_run_collected.rename( columns={ "mode" : "mode_bnb"}, inplace=True )
# Merge Numi
pot_run_collected = pot_run_collected.join( pot_daily_numi.set_index("day"), on="day" )
pot_run_collected.rename( columns={ "pot" : "pot_numi_delivered"}, inplace=True )
pot_run_collected.rename( columns={ "spill" : "spill_numi_delivered"}, inplace=True )
pot_run_collected.rename( columns={ "mode" : "mode_numi"}, inplace=True )

pot_run_collected["ratio_bnb"] = pot_run_collected["pot_bnb_collected"] / pot_run_collected["pot_bnb_delivered"]
pot_run_collected["ratio_numi"] = pot_run_collected["pot_numi_collected"] / pot_run_collected["pot_numi_delivered"]

pot_run_collected = pot_run_collected.sort_values('day')

## strip df by time range

pot_run_collected = pot_run_collected[ pd.to_datetime( pot_run_collected['day'] ) >= pd.to_datetime( start_day ) ]
pot_run_collected = pot_run_collected[ pd.to_datetime( pot_run_collected['day'] ) <= pd.to_datetime( end_day ) ]

print(pot_run_collected)
print("\n@@ Sum")

# BNB info
## POT
pot_bnb_sum_delivered = np.sum(pot_run_collected["pot_bnb_delivered"])
pot_bnb_sum_collected = np.sum(pot_run_collected["pot_bnb_collected"])
bnb_eff = 0.
if pot_bnb_sum_delivered>0.:
  bnb_eff = pot_bnb_sum_collected/pot_bnb_sum_delivered
## Up time
spill_bnb_sum_delivered = np.sum(pot_run_collected["spill_bnb_delivered"])
bnb_pot_uptime = spill_bnb_sum_delivered / ( BNB_MaximumRate * timeInterval.total_seconds() )
print("BNB uptime = %1.3f"%(bnb_pot_uptime))
##TODO
bnb_pot_uptime = 0.
## Mode (assuming the mode is not changed within a week)
bnb_mode = "none"
for i in range(pot_run_collected.shape[0]):
  if pot_run_collected.iloc[i]['mode_bnb']!="none":
    bnb_mode = pot_run_collected.iloc[i]['mode_bnb']
    break

# NuMI info
## POT
pot_numi_sum_delivered = np.sum(pot_run_collected["pot_numi_delivered"])
pot_numi_sum_collected = np.sum(pot_run_collected["pot_numi_collected"])
numi_eff = 0.
if pot_numi_sum_delivered>0.:
  numi_eff = pot_numi_sum_collected/pot_numi_sum_delivered
## Up time
spill_numi_sum_delivered = np.sum(pot_run_collected["spill_numi_delivered"])
numi_pot_uptime = spill_numi_sum_delivered / ( NuMI_MaximumRate * timeInterval.total_seconds() )
print("NuMI uptime = %1.3f"%(numi_pot_uptime))
##TODO
numi_pot_uptime = 0.
## Mode (assuming the mode is not changed within a week)
numi_mode = "none"
for i in range(pot_run_collected.shape[0]):
  if pot_run_collected.iloc[i]['mode_numi']!="none":
    numi_mode = pot_run_collected.iloc[i]['mode_numi']
    break


## FermiDash

UpdateDev = args.dev
UpdateProd = args.prod

dsnHost = "ccdapps-dev.fnal.gov" if UpdateDev else "ccdapps-prod.fnal.gov"
dsnPort = 1535 if UpdateDev else 1539
dsnServiceName = "ccdappsd.fnal.gov" if UpdateDev else "ccdappsp.fnal.gov"

print("\n@@ Updadting %s"%(dsnHost))

dsn = f"{dsnHost}:{dsnPort}/{dsnServiceName}"
conn_Fermi = oracledb.connect(user=ICARUSACCOUNT, password=ICARUSPWD, dsn=dsn)

cur_Fermi = conn_Fermi.cursor()

## Adding BNB
sql = """
INSERT INTO science.detector_interface
(EXPERIMENT_NAME,BEAM_SOURCE,BEAM_MODE,REPORTING_START_DATE,REPORTING_END_DATE,POT_DELIVERED,POT_RECORDED,POT_UPTIME,POT_WEIGHTED_UPTIME,DETECTOR_COMMENTS)
VALUES('ICARUS', 'BNB', '%s', TO_DATE('%s','yyyy-mm-dd'), TO_DATE('%s', 'yyyy-mm-dd'), %f, %f, %f, %f, '')
"""%(bnb_mode, start_day, end_day, pot_bnb_sum_delivered*1E12, pot_bnb_sum_collected*1E12, bnb_pot_uptime, bnb_eff*100. )

print("\n@@ BNB SQL command:")
print(sql)

if not DoNotCommit:
  cur_Fermi.execute(sql)
  conn_Fermi.commit()
  print("-> BNB is updated")

## Adding NuMI
sql = """
INSERT INTO science.detector_interface
(EXPERIMENT_NAME,BEAM_SOURCE,BEAM_MODE,REPORTING_START_DATE,REPORTING_END_DATE,POT_DELIVERED,POT_RECORDED,POT_UPTIME,POT_WEIGHTED_UPTIME,DETECTOR_COMMENTS)
VALUES('ICARUS', 'NuMI', '%s', TO_DATE('%s','yyyy-mm-dd'), TO_DATE('%s', 'yyyy-mm-dd'), %f, %f, %f, %f, '')
"""%(numi_mode, start_day, end_day, pot_numi_sum_delivered*1E12, pot_numi_sum_collected*1E12, numi_pot_uptime, numi_eff*100. )

print("\n@@ NuMI SQL command:")
print(sql)

if not DoNotCommit:
  cur_Fermi.execute(sql)
  conn_Fermi.commit()
  print("-> NuMI is updated")

