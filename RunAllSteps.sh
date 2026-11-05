#!/bin/bash

# start="2026-01-05"
# end="2026-01-11"

# start="2026-02-16"
# end="2026-02-22"

# start="2022-06-09"
# end="2026-02-22"

start="2026-10-25"
end="2026-11-01"

#source getDAQLog.sh
python ParseDAQLog.py -i ${start} -f ${end}
python pot_account.py update-daily-pot ${start} ${end} True
python pot_account.py update-daily-runs ${start} ${end} True
python pot_account.py make-daq-plots ${start} ${end}

