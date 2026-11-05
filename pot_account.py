import sys
import click

import numpy as np
import pandas as pd

import os, sys

from beaminfo.simple_query import query_full_day
from utils.dbmanager import add_day_pot_beam, create_connection, remove_day_pot_beam, remove_daily_collected_pot
from runinfo.read_run_info import insert_daily_runs, make_timestamp, get_day_range

# from plotting.plots_utils import makeCumulativePOTPlot

from plotting.plots_utils import potEfficiency, potCumulative, daqEfficiency, intensityAndCumulativePot, makeCumulativePOTPlot

USER = os.environ['USER']
potDir = os.environ['potDir']

masterDBName = "RunSummary.db"

sys.path.append(potDir)

#######################################################################################################

@click.group("pot_evaluation")
@click.pass_context
def cli(ctx):
    '''
    POT Evaluation commands

    '''

#######################################################################################################

@cli.command("update-daily-pot")
@click.argument("start_day")
@click.argument("end_day")
@click.argument("override")
@click.pass_context
def update_daily_pot( ctx, start_day="", end_day="", override=False ):
    """
    Update the delivered POT for both beam: 
    Args: 
        start_day : string with the day with the values to update in the format "yyyy-mm-dd"
        end_dat : string with the day with the values to update in the format "yyyy-mm-dd"
        override: delete if a row for that day already exists 
    Returs: 
        None
    """

    print("@@ Connecting to %s/dbase/%s"%(potDir,masterDBName))
    conn = create_connection("%s/dbase/%s"%(potDir,masterDBName))

    if conn is not None:

        print( "Updating the POT delivered between : {} ~ {}".format(start_day,end_day) )

        days = get_day_range(start_day,end_day)
        for day in days:
          if override:
              print( "Remove existing rows with key on: {}".format(day) )

              remove_day_pot_beam(conn, day, "bnb")
              remove_day_pot_beam(conn, day, "numi")
          
          ts_start_day = make_timestamp( day+" 00:00:00 CDT", "%Y-%m-%d %H:%M:%S %Z" )
          ts_end_day   = make_timestamp( day+" 23:59:59 CDT", "%Y-%m-%d %H:%M:%S %Z" )

          numi_beam_info = query_full_day(ts_start_day,ts_end_day, "numi")
          bnb_beam_info = query_full_day(ts_start_day,ts_end_day, "bnb")

          add_day_pot_beam( conn, ( day, numi_beam_info[0], numi_beam_info[1], numi_beam_info[2], numi_beam_info[3]), "numi" )
          add_day_pot_beam( conn, ( day, bnb_beam_info[0], bnb_beam_info[1], bnb_beam_info[2], bnb_beam_info[3]), "bnb")

          #add_day_beam_info( conn, day, ts_start_day, ts_end_day, "numi" )
          
          print(" ALL pot delivered information updated for day {} ".format(day))
         
    else:

      print("FAILED CONNECTION")


#######################################################################################################

@cli.command("update-daily-runs")
@click.argument("start_day")
@click.argument("end_day")
@click.argument("override")
@click.pass_context
def update_daily_runs( ctx, start_day="", end_day="", override=False ):
    """
    Update the collected POT associated to a run for both beam: 
    Args: 
        day: string with the day with the values to update in the format "yyyy-mm-dd"
        override: delete if a row for that day already exists 
    Returs: 
        None
    """

    conn = create_connection("%s/dbase/%s"%(potDir, masterDBName))

    if conn is not None:

        print( "@@ Updating the POT collected between : {} ~ {}".format(start_day,end_day) )

        days = get_day_range(start_day,end_day)
        for day in days:
          if override:
            print( "Remove existing rows with key on: {}".format(day) )
            remove_daily_collected_pot( conn, day )

          insert_daily_runs( conn, day )
        print( "@@ -> ALL pot collected information updated between : {} ~ {}".format(start_day,end_day) )

    else:

        print("FAILED CONNECTION")

#######################################################################################################

@cli.command("make-daq-plots")
@click.pass_context
@click.argument("start_day")
@click.argument("end_day")
def make_daq_plots( ctx, start_day="", end_day="" ):
    """
    Make the daq plots with the new day information
    """

    if start_day=="":
        start_day="2021-05-31"
    if end_day=="":
        end_day=today.strftime("%Y-%m-%d")

    time_range = (start_day, end_day)

    print("Potting between {} and {}".format(start_day, end_day) )

    conn = create_connection("%s/dbase/%s"%(potDir, masterDBName))

    if conn is None:
        print("FAILED CONNECTION")
    
    pot_run_collected = pd.read_sql( "SELECT * from daily_collected_pot", conn )
    pot_daily_bnb = pd.read_sql( "SELECT * from day_pot_bnb", conn )
    pot_daily_numi = pd.read_sql( "SELECT * from day_pot_numi", conn )

    # Per-configuration runtime over the requested window
    ts_start_range = make_timestamp( start_day+" 00:00:00 CDT", "%Y-%m-%d %H:%M:%S %Z" )
    ts_end_range   = make_timestamp( end_day+" 23:59:59 CDT", "%Y-%m-%d %H:%M:%S %Z" )
    run_timestamp = pd.read_sql(
        "SELECT run, start, stop, conf FROM run_timestamp WHERE (stop>=%d) AND (start<=%d)"%(ts_start_range, ts_end_range),
        conn )

    conn.close()

    # Merge BNB
    pot_run_collected = pot_run_collected.join( pot_daily_bnb.set_index("day"), on="day" )
    pot_run_collected.rename( columns={ "pot" : "pot_bnb_delivered", "spill" : "spill_bnb_delivered", "mode" : "mode_bnb", "beam_on_time" : "beam_on_time_bnb"}, inplace=True )
    # Merge Numi
    pot_run_collected = pot_run_collected.join( pot_daily_numi.set_index("day"), on="day" )
    pot_run_collected.rename( columns={ "pot" : "pot_numi_delivered", "spill" : "spill_numi_delivered", "mode" : "mode_numi", "beam_on_time" : "beam_on_time_numi"}, inplace=True )

    pot_run_collected["ratio_bnb"] = pot_run_collected["pot_bnb_collected"] / pot_run_collected["pot_bnb_delivered"]
    pot_run_collected["ratio_numi"] = pot_run_collected["pot_numi_collected"] / pot_run_collected["pot_numi_delivered"]

    pot_run_collected["bnb_intensity"] = pot_run_collected["pot_bnb_delivered"]/ pot_run_collected["spill_bnb_delivered"]*1E12
    pot_run_collected["numi_intensity"] = pot_run_collected["pot_numi_delivered"]/ pot_run_collected["spill_numi_delivered"]*1E12

    pot_run_collected = pot_run_collected.sort_values('day')
    pot_run_collected_alltime = pot_run_collected

    ## strip df by time range

    pot_run_collected = pot_run_collected[ pd.to_datetime( pot_run_collected['day'] ) >= pd.to_datetime( start_day ) ]
    pot_run_collected = pot_run_collected[ pd.to_datetime( pot_run_collected['day'] ) <= pd.to_datetime( end_day ) ]

    ## Print final DataGrame

    print(pot_run_collected)

    ## Median

    print("@@ Medians")

    print("pot_bnb_collected = ",  np.median(pot_run_collected["pot_bnb_collected"]) )
    print("pot_numi_collected = ", np.median(pot_run_collected["pot_numi_collected"]) )

    print("pot_bnb_delivered = ",  np.median(pot_run_collected["pot_bnb_delivered"]) )
    print("pot_numi_delivered = ", np.median(pot_run_collected["pot_numi_delivered"]) )

    print("ratio_bnb = ",  np.median(pot_run_collected["ratio_bnb"]) )
    print("ratio_numi = ", np.median(pot_run_collected["ratio_numi"]) )
    print("runtime = ",  np.median(pot_run_collected["runtime"]) )

    ## Sum

    print("@@ Sum")

    print("BNB")
    print("- Delivered = %1.2e POT, %d spills"%(np.sum(pot_run_collected["pot_bnb_delivered"])*1E12, np.sum(pot_run_collected["spill_bnb_delivered"])) )
    print("- Collected = %1.2e POT, %d spills"%(np.sum(pot_run_collected["pot_bnb_collected"])*1E12, np.sum(pot_run_collected["spill_bnb_collected"])) )
    print("- Collected/Delivered = %1.3f"%(np.sum(pot_run_collected["pot_bnb_collected"])/np.sum(pot_run_collected["pot_bnb_delivered"])) )
    print("NuMI")
    print("- Delivered = %1.2e POT, %d spills"%(np.sum(pot_run_collected["pot_numi_delivered"])*1E12, np.sum(pot_run_collected["spill_numi_delivered"])) )
    print("- Collected = %1.2e POT, %d spills"%(np.sum(pot_run_collected["pot_numi_collected"])*1E12, np.sum(pot_run_collected["spill_numi_collected"])) )
    print("- Collected/Delivered = %1.3f"%(np.sum(pot_run_collected["pot_numi_collected"])/np.sum(pot_run_collected["pot_numi_delivered"])) )
    sumRunTime = np.sum(pot_run_collected["runtime"])
    print("Runtime = %d sec"%( int(sumRunTime) ) )
    print("        = %1.1f hrs"%( sumRunTime/3600. ) )
    print("        = %1.1f days"%( sumRunTime/3600./24. ) )

    ## DAQ runtime statistics

    print("@@ DAQ runtime statistics")

    runtime = pot_run_collected["runtime"]
    beam_on_time = pot_run_collected["beam_on_time_bnb"].fillna(0) \
                 + pot_run_collected["beam_on_time_numi"].fillna(0)

    total_live_time = np.sum(runtime)
    avg_run_time = np.mean(runtime)

    rt_clipped = run_timestamp.copy()
    rt_clipped["start"] = rt_clipped["start"].clip(lower=ts_start_range)
    rt_clipped["stop"]  = rt_clipped["stop"].clip(upper=ts_end_range)
    rt_clipped["duration"] = rt_clipped["stop"] - rt_clipped["start"]
    total_live_time_all = rt_clipped["duration"].sum()
    max_run_time = rt_clipped["duration"].max()

    sum_beam_on_time = np.sum(beam_on_time)
    beam_weighted_up_time = np.sum(runtime * beam_on_time) / sum_beam_on_time \
                            if sum_beam_on_time > 0 else float("nan")

    print("Total live time (all configs)    = %d sec (%1.1f hrs, %1.1f days)"%( int(total_live_time_all), total_live_time_all/3600., total_live_time_all/3600./24. ) )
    print("Total live time (physics only)   = %d sec (%1.1f hrs, %1.1f days)"%( int(total_live_time), total_live_time/3600., total_live_time/3600./24. ) )
    print("Average run time     = %d sec (%1.1f hrs)"%( int(avg_run_time), avg_run_time/3600. ) )
    print("Max run time         = %d sec (%1.1f hrs)"%( int(max_run_time), max_run_time/3600. ) )
    print("Beam-weighted avg. physics DAQ uptime = %d sec/day (%1.1f hrs/day)"%( int(beam_weighted_up_time), beam_weighted_up_time/3600. ) )
    beam_weighted_up_fraction = beam_weighted_up_time / 86400. \
                                if sum_beam_on_time > 0 else float("nan")
    print("                                       = %1.3f fraction of a day (NOT a total over the range; weighted toward beam-heavy days)"%( beam_weighted_up_fraction ) )

    ## Exact overlap: time beam was actually on AND a physics-config DAQ run was recording,
    ## summed over the requested range (computed per-day at ingestion time in
    ## runinfo/read_run_info.py by querying beam livetime restricted to the physics-config
    ## run windows, unlike beam_on_time_bnb/numi which cover the whole calendar day).
    beam_on_time_bnb_physics = pot_run_collected.get("beam_on_time_bnb_physics", pd.Series(dtype=float)).fillna(0)
    beam_on_time_numi_physics = pot_run_collected.get("beam_on_time_numi_physics", pd.Series(dtype=float)).fillna(0)
    sum_bnb_overlap = np.sum(beam_on_time_bnb_physics)
    sum_numi_overlap = np.sum(beam_on_time_numi_physics)

    # "Total time there was beam" = full calendar-day beam-on time (beam_on_time_bnb/numi,
    # already loaded above), independent of what the DAQ was doing - the denominator for
    # "of all the time there was beam, what fraction did physics-config DAQ record".
    sum_bnb_beam_on_total  = np.sum(pot_run_collected["beam_on_time_bnb"].fillna(0))
    sum_numi_beam_on_total = np.sum(pot_run_collected["beam_on_time_numi"].fillna(0))
    bnb_overlap_frac  = sum_bnb_overlap / sum_bnb_beam_on_total  if sum_bnb_beam_on_total  > 0 else float("nan")
    numi_overlap_frac = sum_numi_overlap / sum_numi_beam_on_total if sum_numi_beam_on_total > 0 else float("nan")

    print("BNB beam-on AND physics-config recording  = %d sec (%1.1f hrs)"%( int(sum_bnb_overlap), sum_bnb_overlap/3600. ) )
    print("                                           / Total BNB beam-on = %d sec (%1.1f hrs) = %1.3f"%( int(sum_bnb_beam_on_total), sum_bnb_beam_on_total/3600., bnb_overlap_frac ) )
    print("NuMI beam-on AND physics-config recording = %d sec (%1.1f hrs)"%( int(sum_numi_overlap), sum_numi_overlap/3600. ) )
    print("                                           / Total NuMI beam-on = %d sec (%1.1f hrs) = %1.3f"%( int(sum_numi_beam_on_total), sum_numi_beam_on_total/3600., numi_overlap_frac ) )

    ## Runtime per configuration

    print("@@ Runtime per configuration")

    conf_runtime = run_timestamp.copy()
    # Clip each run to the requested window so partially-overlapping runs count only the in-window part
    conf_runtime["start"] = conf_runtime["start"].clip(lower=ts_start_range)
    conf_runtime["stop"]  = conf_runtime["stop"].clip(upper=ts_end_range)
    conf_runtime["duration"] = conf_runtime["stop"] - conf_runtime["start"]
    conf_runtime = conf_runtime.groupby("conf")["duration"].sum().sort_values(ascending=False)

    # Mirrors POTConfPattern from runinfo/read_run_info.py (case-insensitive, SQLite LIKE semantics)
    def _is_physics_conf(conf):
        cl = conf.lower()
        return ("calibration" not in cl) and (
            "physics" in cl or "majority" in cl or "test_thr390_" in cl
        )

    physics_total = 0.
    for conf, duration in conf_runtime.items():
        print("%-40s = %d sec (%1.1f hrs, %1.1f days)"%( conf, int(duration), duration/3600., duration/3600./24. ) )
        if _is_physics_conf(conf):
            physics_total += duration

    print("%-40s = %d sec (%1.1f hrs, %1.1f days)"%( "Physics-config subtotal", int(physics_total), physics_total/3600., physics_total/3600./24. ) )

    # MAKE PLOTS, SAVE THEM 
    potEfficiency(pot_run_collected, "bnb", time_range)\
        .savefig("fig/eff_pot_bnb.png")
    
    potEfficiency(pot_run_collected, "numi", time_range)\
        .savefig("fig/eff_pot_numi.png")
    
    potCumulative(pot_run_collected, ["numi", "bnb"], time_range)\
        .savefig("fig/cumulative_pot_numi_bnb.png")
    
    potCumulative(pot_run_collected, ["numi"], time_range)\
        .savefig("fig/cumulative_pot_numi.png")
    
    potCumulative(pot_run_collected, ["bnb"], time_range)\
        .savefig("fig/cumulative_pot_bnb.png")

    daqEfficiency( pot_run_collected, time_range )\
        .savefig("fig/eff_daq_numi_bnb.png")
    
    intensityAndCumulativePot( pot_run_collected, "bnb", time_range)\
        .savefig("fig/intensity_and_cumulative_pot_bnb.png")

    intensityAndCumulativePot( pot_run_collected, "numi", time_range)\
        .savefig("fig/intensity_and_cumulative_pot_numi.png")


    startDay, endDay = time_range

    makeCumulativePOTPlot( 
        pot_run_collected_alltime, 
        ('2022-06-09', '2022-07-09'), 
        ('2022-12-20', '2023-07-14'), 
        ('2024-03-14', '2024-07-10'), 
        ('2024-12-10', '2025-07-07'),
        ('2025-10-16', '2026-06-13'),
        ('2026-10-01', endDay)
    )\
        .savefig(f"fig/collected_both_up_to{endDay}.png")
    
    return

#######################################################################################################

# @cli.command("make-runbyrun-plots")
# @click.pass_context
# @click.argument("run")

# def make_runbyrun_plots( ctx, run=""):
#     """
#     Make the daq plots with the new day information
#     TODO: select range
#     """
#     conn = create_connection("%s/dbase/run02_beaminfo.db"%(potDir))

#     if conn is None:
#         print("FAILED CONNECTION")
    
#     pot_daily_run=pd.read_sql( "SELECT * from run_day_pot", conn )
#     pot_run_=pd.read_sql( "SELECT * from run_pot", conn )

#     pot_run.to_csv('dumpbnb.csv')
#     conn.close()

#     # DB Manipulation
#     pot_run_collected = pd.DataFrame(pot_run)
#     print(pot_run_collected[1]) 
    
#     return

def main():
    cli(obj=dict())


if '__main__' == __name__:
    main()
