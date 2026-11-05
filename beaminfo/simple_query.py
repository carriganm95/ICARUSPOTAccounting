import urllib.request, urllib.error, sys, os, time

import numpy as np

beamdburl = os.environ["beamdburl"]

def _urlopen_with_retry(url, retries=3, delay=10):
    for attempt in range(1, retries + 1):
        try:
            return urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            if e.code == 504 and attempt < retries:
                print(f'WARNING: HTTP 504 (attempt {attempt}/{retries}), retrying in {delay}s ...')
                time.sleep(delay)
            else:
                raise

def parse_line(line):
#  print('line',line)
  line = ( line.strip() ).decode('utf-8')
#  print('line',line)
  buff = line.split(",")
#  print('buff',buff)
  return float(buff[5])

def parse_line_with_time(line):
  # CSV columns: Event,Variable,Clock(ms),Units,Value
  # "e,<event>" is quoted so splits into buff[0]="e  buff[1]=<event>"
  # buff[3] = clock in milliseconds, buff[4] = units, buff[5] = value
  line = ( line.strip() ).decode('utf-8')
  buff = line.split(",")
  return float(buff[3]) / 1000.0, float(buff[5])


def query_beam_livetime( t0, t1, device_name, event, min_pot=0.1 ):
  """
  Compute beam-on time (seconds) from real spill count × median cycle time.
  min_pot (E12 units) filters Booster RF noise (~5e-4 E12) and accelerator
  studies (max ~0.02 E12) from real physics beam (~4.5 E12 for BNB).
  """
  url = "%s/data?v=%s&e=e,%s&t0=%d&t1=%d&f=csv" % (beamdburl, device_name, event, t0, t1)

  try:
    f = _urlopen_with_retry(url)
  except urllib.error.HTTPError as e:
    print(f'WARNING: HTTP {e.code} for {url} — returning 0.0 beam livetime')
    return 0.

  timestamps = []
  for i, line in enumerate(f):
    if i == 0:
      continue
    ts, pot = parse_line_with_time(line)
    if pot > min_pot:
      timestamps.append(ts)

  if len(timestamps) < 2:
    return 0.

  timestamps = np.sort(timestamps)
  median_interval = float(np.median(np.diff(timestamps)))
  beam_on_time = len(timestamps) * median_interval
  print(f'beam livetime {device_name}: n_real_spills={len(timestamps)} cycle={median_interval:.3f}s beam_on={beam_on_time:.1f}s')
  return beam_on_time


def query_pot_interval( t0, t1, device_name, event, debug=False ):

  url = "%s/data?v=%s&e=e,%s&t0=%d&t1=%d&f=csv" % (beamdburl, device_name, event, t0, t1)

  print(url)

  if debug:
    print( "URL:", url )

  try:
    f = _urlopen_with_retry(url)
  except urllib.error.HTTPError as e:
    print(f'WARNING: HTTP {e.code} for {url} — returning (0, 0)')
    return 0., 0

  if debug:
    print( "Status code: %s\n" % (f.getcode(),) )

  pot = 0.
  spill = 0
  for i, line in enumerate(f):
    if i==0:
      continue
    pot += parse_line(line)
    spill += 1
  print('interval t0',t0,'t1',t1,'pot',pot,'spill',spill,'device',device_name)
  return pot, spill


def query_full_day_pot(ts_start, ts_end, device_name, event, debug=False ):

  url = "%s/data?v=%s&e=e,%s&t0=%d&t1=%d&f=csv" % (beamdburl, device_name, event, ts_start, ts_end)

  if debug:
    print( "URL:", url )

  try:
    f = _urlopen_with_retry(url)
  except urllib.error.HTTPError as e:
    print(f'WARNING: HTTP {e.code} for {url} — returning (0, 0)')
    return 0., 0

  if debug:
    print( "Status code: %s\n" % (f.getcode(),) )

  pot = 0.
  spill = 0
  for i, line in enumerate(f):
    if i==0:
      continue
    pot += parse_line(line)
    spill += 1
  print('full day t0',ts_start,'t1',ts_end,'pot',pot,'spill',spill,'device',device_name)
  return pot, spill

def get_full_day_horncurrent(ts_start, ts_end, device_name, event, debug=False ):

  url = "%s/data?v=%s&e=e,%s&t0=%d&t1=%d&f=csv" % (beamdburl, device_name, event, ts_start, ts_end)

  if debug:
    print( "URL:", url )

  print(url)

  try:
    f = _urlopen_with_retry(url)
  except urllib.error.HTTPError as e:
    print(f'WARNING: HTTP {e.code} for {url} — returning 0.0 avg current')
    return 0.

  if debug:
    print( "Status code: %s\n" % (f.getcode(),) )

  totalcount = 0.
  sumcurrent = 0.
  for i, line in enumerate(f):
    if i==0:
      continue
    this_current = parse_line(line)
    #print("get_full_day_horncurrent", device_name, this_current)
    if abs(this_current)>10.:
      totalcount += 1.
      sumcurrent += this_current
  avgcurrent = 0.
  if totalcount>0.:
    avgcurrent = sumcurrent/totalcount
  print('full day sum current',ts_start,'t1',ts_end,'sum_current',sumcurrent,'avg_current',avgcurrent,'device',device_name)

  return avgcurrent

def query_full_day( ts_start_day, ts_end_day, beam ):

  ## pot

  pot_db_device = "E:TORTGT" if beam=="numi" else "E:TOR875" # else = bnb
  pot_db_event = "a9" if beam=="numi" else "1d" # else = bnb

  pot, spill = query_full_day_pot(ts_start_day, ts_end_day, pot_db_device, pot_db_event)

  ## horn current

  hc_db_device = "E:HRNDIR" if beam=="numi" else "E:THCURR" # else = bnb
  hc_db_event = "a9" if beam=="numi" else "1d" # else = bnb

  hc = get_full_day_horncurrent(ts_start_day, ts_end_day, hc_db_device, hc_db_event)

  mode = "none"
  if beam=="numi":
    if hc<0:
      mode = "nu"
    elif hc>0:
      mode = "nubar"
  elif beam=="bnb":
    if hc>0:
      mode = "nu"
    elif hc<0:
      mode = "nubar"

  ## beam-on time from spill timestamps
  beam_on_time = query_beam_livetime(ts_start_day, ts_end_day, pot_db_device, pot_db_event)

  return [pot, spill, mode, beam_on_time]
  
