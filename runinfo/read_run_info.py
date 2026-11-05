import sys, os
import time
import datetime
import numpy as np
import pandas as pd

potDir = os.environ['potDir']

from utils.dbmanager import add_run_day_pot, add_run_pot, create_connection

from beaminfo.simple_query import query_pot_interval, query_beam_livetime

def make_timestamp( time_string, string_format="%Y-%b-%d %H:%M:%S %Z" ):

    timestamp=datetime.datetime.strptime(time_string, string_format)
    #print("timestamp",timestamp)
    return int(time.mktime(timestamp.timetuple()))

def get_day_range(start_day, end_day):

  ret = []
  start_day_date = datetime.date.fromisoformat(start_day)
  end_day_date = datetime.date.fromisoformat(end_day)
  delta = datetime.timedelta(days=1)
  while start_day_date <= end_day_date:
    ret.append( start_day_date.strftime("%Y-%m-%d") )
    start_day_date += delta
  return ret


def parse_line( line ):
    # example Thu Jun 30 12:24:37 CDT 2022: STOP transition complete for run 8524

    buff = line.split(": ") #mind the space for correct string parsing
#    date_info = buff[0].split(" ")
#    run_info  = buff[1].split(" ")
    date_info = buff[0].split()
    run_info  = buff[1].split(" ")
    month = date_info[1]
    day   = date_info[2]
    times = date_info[3]
    zone  = date_info[4]
    year  = date_info[5]
    run   = run_info[-1]

    #Form the timestamp 
    day_string = "-".join([ year, month, day ])

    time_string=day_string+" "+times+" "+zone
    #print("date_info",date_info)
    #print("time",time_string)
    return run, make_timestamp(time_string)

def insert_daily_runs( conn, day_string ):

    ## Only count Physics or Majority configs, and skip Calibration
    #POTConfPattern = '''NOT (conf LIKE "%Calibration%") AND ( (conf LIKE "%physics%") OR (conf LIKE "%majority%") )'''
    POTConfPattern = '''NOT (conf LIKE "%Calibration%") AND ( (conf LIKE "%physics%") OR (conf LIKE "%majority%") OR (conf LIKE "%Test_thr390_%") )'''

    ## Cound all configuration
    #POTConfPattern = '1' ## debugging

    # Use the day_string to get the UNIX timestamps of the start-end of the day
    ts_start_day = make_timestamp( day_string+" 00:00:00 CDT", "%Y-%m-%d %H:%M:%S %Z" )
    ts_end_day   = make_timestamp( day_string+" 23:59:59 CDT", "%Y-%m-%d %H:%M:%S %Z" )

    # Getting the current date and time
    dt_now = datetime.datetime.now()
    ts_now = datetime.datetime.timestamp(dt_now)
    if ts_now<ts_end_day:
      print("@@ Now %s is not finished.. replacing \"ts_end_day\" to now")
      ts_end_day = ts_now

    ## Run timestamp db

    print("@@ Day: %s"%(day_string))
    print("@@ ts_start_day = %d"%(ts_start_day))
    print("@@ ts_end_day = %d"%(ts_end_day))

    ToMergedDF = []

    run_prev = pd.read_sql( "SELECT * FROM run_timestamp WHERE (start<%d) AND (stop>=%d) AND (%s)"%(ts_start_day,ts_start_day,POTConfPattern), conn )
    if run_prev.shape[0]>0:
      print("@@ Run prev")
      print(run_prev)
      run_prev.at[0,"start"] = ts_start_day
      if run_prev.at[0,"stop"]>=ts_end_day:
        run_prev.at[0,"stop"] = ts_end_day
      ToMergedDF.append(run_prev)

    run_contained = pd.read_sql( "SELECT * FROM run_timestamp WHERE (start>=%d) AND (stop<%d) AND (%s)"%(ts_start_day,ts_end_day,POTConfPattern), conn )
    if run_contained.shape[0]>0:
      print("@@ Run contained")
      print(run_contained)
      ToMergedDF.append(run_contained)

    run_continued = pd.read_sql( "SELECT * FROM run_timestamp WHERE (start BETWEEN %d AND %d) AND (stop>=%d) AND (%s)"%(ts_start_day,ts_end_day,ts_end_day, POTConfPattern), conn )
    if run_continued.shape[0]>0:
      print("@@ Run continued")
      print(run_continued)
      run_continued.at[0,"stop"] = ts_end_day
      ToMergedDF.append(run_continued)

    # Compute total DAQ runtime for any run config (no filter)
    run_all_prev = pd.read_sql( "SELECT * FROM run_timestamp WHERE (start<%d) AND (stop>=%d)"%(ts_start_day,ts_start_day), conn )
    run_all_contained = pd.read_sql( "SELECT * FROM run_timestamp WHERE (start>=%d) AND (stop<%d)"%(ts_start_day,ts_end_day), conn )
    run_all_continued = pd.read_sql( "SELECT * FROM run_timestamp WHERE (start BETWEEN %d AND %d) AND (stop>=%d)"%(ts_start_day,ts_end_day,ts_end_day), conn )

    ToAllDF = []
    if run_all_prev.shape[0]>0:
      run_all_prev = run_all_prev.copy()
      run_all_prev.at[0,"start"] = ts_start_day
      if run_all_prev.at[0,"stop"]>=ts_end_day:
        run_all_prev.at[0,"stop"] = ts_end_day
      ToAllDF.append(run_all_prev)
    if run_all_contained.shape[0]>0:
      ToAllDF.append(run_all_contained)
    if run_all_continued.shape[0]>0:
      run_all_continued = run_all_continued.copy()
      run_all_continued.at[0,"stop"] = ts_end_day
      ToAllDF.append(run_all_continued)

    sum_runtime_all = 0.
    if len(ToAllDF)>0:
      df_all = pd.concat(ToAllDF, ignore_index=True)
      for i in range(0, df_all.shape[0]):
        sum_runtime_all += df_all.at[i,"stop"] - df_all.at[i,"start"]

    if len(ToMergedDF)==0:

      sql = "INSERT INTO daily_collected_pot(day, pot_bnb_collected, spill_bnb_collected, pot_numi_collected, spill_numi_collected, runtime, runtime_all, beam_on_time_bnb_physics, beam_on_time_numi_physics) VALUES(?,?,?,?,?,?,?,?,?)"
      add_row = (day_string, 0., 0, 0., 0, 0., sum_runtime_all, 0., 0.)

      cur = conn.cursor()
      cur.execute(sql, add_row)
      conn.commit()

      return

    df_merged = pd.concat(ToMergedDF, ignore_index=True)
    print("@@ Final intervals")
    print(df_merged)

    sum_pot_bnb_value = 0.
    sum_spill_bnb_value = 0
    sum_pot_numi_value = 0.
    sum_spill_numi_value = 0
    sum_runtime = 0.
    sum_beam_on_time_bnb_physics = 0.
    sum_beam_on_time_numi_physics = 0.

    for i in range(0,df_merged.shape[0]):
      run = df_merged.at[i,"run"]
      start = df_merged.at[i,"start"]
      stop = df_merged.at[i,"stop"]

      pot_bnb_value, spill_bnb_value =  query_pot_interval(start, stop, "E:TOR875", "1d")
      pot_numi_value, spill_numi_value  = query_pot_interval(start, stop, "E:TORTGT", "a9")
      runtime = stop-start

      # Beam livetime (seconds of real spills) restricted to this physics-config
      # run window, i.e. actual overlap between "beam on" and "physics DAQ recording",
      # as opposed to beam_on_time_bnb/numi in day_pot_bnb/numi which cover the
      # whole calendar day regardless of what the DAQ was doing.
      beam_on_time_bnb_physics = query_beam_livetime(start, stop, "E:TOR875", "1d")
      beam_on_time_numi_physics = query_beam_livetime(start, stop, "E:TORTGT", "a9")

      sum_pot_bnb_value += pot_bnb_value
      sum_spill_bnb_value += spill_bnb_value
      sum_pot_numi_value += pot_numi_value
      sum_spill_numi_value += spill_numi_value
      sum_runtime += runtime
      sum_beam_on_time_bnb_physics += beam_on_time_bnb_physics
      sum_beam_on_time_numi_physics += beam_on_time_numi_physics

      #print(run,start,stop,pot_bnb_value,pot_numi_value)

    print(day_string, sum_pot_bnb_value, sum_pot_numi_value, sum_runtime)

    sql = "INSERT INTO daily_collected_pot(day, pot_bnb_collected, spill_bnb_collected, pot_numi_collected, spill_numi_collected, runtime, runtime_all, beam_on_time_bnb_physics, beam_on_time_numi_physics) VALUES(?,?,?,?,?,?,?,?,?)"
    add_row = (day_string, sum_pot_bnb_value, sum_spill_bnb_value, sum_pot_numi_value, sum_spill_numi_value, sum_runtime, sum_runtime_all, sum_beam_on_time_bnb_physics, sum_beam_on_time_numi_physics)

    cur = conn.cursor()
    cur.execute(sql, add_row)
    conn.commit()


