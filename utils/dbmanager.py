import sqlite3 
from sqlite3 import Error

import os, sys

"""
This script creates the beam, run, pot database for the first time
"""

def create_connection(db_file):
	"""
	Create a new dbase connection
	"""
	conn = None

	try: 

		conn = sqlite3.connect(db_file)

		return conn

	except Error as e:

		print(e)

	return conn


def create_table( conn, create_table_sql ):
	"""
	Create a table from the create_table_sql statement
	:param conn: Connection object
	:param create_table_sql: a CREATE TABLE statement
	"""

	try:

		c = conn.cursor()
		c.execute(create_table_sql)

	except Error as e:
		print(e)

def add_column_if_missing( conn, table, column, column_def ):
	"""
	Idempotently add a column to an existing table (CREATE TABLE IF NOT EXISTS
	does not retrofit columns onto a table that already exists).
	:param conn: Connection object
	:param table: table name
	:param column: column name to check/add
	:param column_def: the SQL type/constraints to use if the column is added,
	                    e.g. "REAL NOT NULL DEFAULT 0"
	"""

	c = conn.cursor()
	existing = [row[1] for row in c.execute("PRAGMA table_info(%s)" % table)]
	if column in existing:
		return False

	c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, column_def))
	conn.commit()
	print("@@ Added column %s to %s" % (column, table))
	return True

def add_run_day_pot( conn, row_insert ):
	"""
	Add to the day_pot_bnb and day_pot_numi
	"""

	sql = "INSERT INTO run_day_pot(run, day, runtime, pot_bnb_collected, pot_numi_collected, trigger) VALUES(?,?,?,?,?,?)"
 
	cur = conn.cursor()
	cur.execute(sql, row_insert)
	conn.commit()

	return cur.lastrowid

def add_run_pot( conn, row_insert ):
	"""
	Add to the run_pot 
	"""
	print("before sql", row_insert)
	sql = "INSERT INTO run_pot(run, runtime, pot_bnb_collected, pot_numi_collected, trigger) VALUES(?,?,?,?,?)"
 
	cur = conn.cursor()
	cur.execute(sql, row_insert)
	conn.commit()
	print('after adding run pot')
	return cur.lastrowid

def remove_run_day_pot( conn, day ):
	"""
	Remove the line of the day
	"""

	sql = "DELETE FROM run_day_pot WHERE day=?"
	cur = conn.cursor()
	cur.execute(sql, (day,))
	conn.commit()

	return 

def add_day_pot_beam( conn, row_insert, beam ):
	"""
	Add to the day_pot_bnb and day_pot_numi
	"""

	sql = "INSERT INTO day_pot_{}(day, pot, spill, mode, beam_on_time) VALUES(?,?,?,?,?)".format(beam)

	cur = conn.cursor()
	cur.execute(sql, row_insert)
	conn.commit()

	return cur.lastrowid


def remove_day_pot_beam( conn, day, beam ):

	sql = "DELETE FROM day_pot_{} WHERE day=?".format(beam)
	cur = conn.cursor()
	cur.execute(sql, (day,))
	conn.commit()

	return 

def remove_daily_collected_pot( conn, day ):

  sql = "DELETE FROM daily_collected_pot WHERE day=?"
  cur = conn.cursor()
  cur.execute(sql, (day,))
  conn.commit()

  return

