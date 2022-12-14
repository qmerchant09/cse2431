import threading
import sys
import argparse
import pathlib
import importlib
import analyze
import re
import glob
import student

TARGET_OOO = 10  # This isn't a real meaningful target.  It's 'global' to this file for convenience, but buffer.py will try to make it a more meaningful value based on the environment.


# Some error/warning strings
error_zero        = "  <<< ERROR:   Should be zero"
error_hundred     = "  <<< ERROR:   Should be 100%"
error_star        = "  <<< ERROR:   Issues marked with a *"
ooo_error         = "  <<< ERROR:   Out of Order should NOT be zero"
ooo_target_warn   = "  <<< WARNING: OOO Low, target is %.1f%%.  Corresponding one-line summaries marked with 'L' but not as bad."
ooo_target_error  = "  <<< ERROR:   Out of Order target average is %.1f%%"
idle_prod_error   = "  <<< ERROR:   Idle producer"
idle_cons_error   = "  <<< ERROR:   Idle consumer"
error_true        = "  <<< ERROR:   Should be TRUE"
error_false       = "  <<< ERROR:   Should be FALSE"
kill_notice       = "  (Note: Test KILLED.)"


# Want to turn raw numbers into percents
def percent(number, base):
    try:              percent = number/base * 100     # Calc percent if good base
    except Exception: percent = 0                     # If bad base, assume percent is zero
    return percent     


# Helped function to consistently output labels for lines
def label(l, delta=0, num=20, colon=True):
    format_str  = "%%-%ds" % (num+delta)
    if colon: return (format_str % ("%s:" % l))
    else:     return (format_str % ("%s"  % l))


# The filename parts have letters next to the numbers.  
# Need to strip the letters, return the textual number as an int.
def filename_part_to_int(token):
    temp = re.sub('[a-zA-Z]','',token)
    try:              return int(temp)
    except Exception: return 0



# The config keys are built and parsed base on the first letter of the text in each part of the name
# While the keys built in the code use one character prefixes, someone could use longer ones
# when they hand edit files.  So, not doing a direct match, using startswith instead.
def parts_from_key(key):
    producers = consumers = slots = items = run_num = 0
    for part in key.split('_'):
        if   part.startswith('p'):  producers = filename_part_to_int(part)        # the producer part starts with 'p'
        elif part.startswith('c'):  consumers = filename_part_to_int(part)        # the consumer part starts with 'c'
        elif part.startswith('s'):  slots     = filename_part_to_int(part)        # the slots    part starts with 's'
        elif part.startswith('i'):  items     = filename_part_to_int(part)        # the items    part starts with 'i'
        elif part.startswith('r'):  run_num   = filename_part_to_int(part)        # the run      part starts with 'r'
    return producers, consumers, slots, items, run_num
    

# The filename will typically have a path, want just the stem to tokenize the parts.
# The stem should be CONFIGNAME_key where the key has a lot of structure.
def parts_from_filename(filename, with_run=True):
    pure  = pathlib.PurePath(filename)                    # Use a PurePath so it's more platform safe, etc.
    parts = pure.stem.lower().split('_')                  # Pull off the stem, put it in lower case, then split on '_' so we can pass on without the CONFIGNAME
    return parts_from_key('_'.join(parts[1:]))            # Return the tokens, but note that the string is rebuilt first without CONFIGNAME
     

# Simple text key for configs
def config_key(producers=0, consumers=0, slots=0, items=0):
    return "p%d_c%d_s%d_i%d" % (producers, consumers, slots, items)


# Want to group runs by their corresponding config keys.  
# So, maintain a dictionary of keys and a config for each
configs_by_key = {}


# Given a filename, find (or create) the corresponding config object for the run
# This function is just used to analyze runs, the 'timeout' isn't 'valid' here, but passing thru to config_object init for completeness.
def config_from_filename(filename, timeout):
    producers, consumers, slots, items, run_num = parts_from_filename(filename)                           # tokenize the name
    key = config_key(producers, consumers, slots, items)                                                  # get clean key from tokens
    if key in configs_by_key: config = configs_by_key[key]                                                # config for key already exists
    else:          
        name   = "CONFIG-%d" % (len(configs_by_key) + 1)                                                  # need to create config, build a 'fake' name
        config = configs_by_key[key] = config_object(name, producers, consumers, slots, items, timeout)   # Now, create config from the name and parts
    return config


SECTION_START = "\n\n\n********************************************************************************************************"
SECTION_END   =       "********************************************************************************************************\n\n"


# This is the main/top config class.  
# It maintains information about a configuration and all the runs that have this config
class config_object():
    def __init__(self, name, producers, consumers, slots, items, timeout):
        self.name = name
        nparts    = name.split('_')
        # Due to the key tokenization, names can't have a '_'
        if len(nparts)>1:
            print("\n\nERROR: config names cannot include an underscore '_'.  Please modify config name '%s' and rerun.\n\n" % name, file=sys.stderr)
            sys.exit(2)
        self.producers     = producers      
        self.consumers     = consumers
        self.slots         = slots
        self.items         = items
        self.key           = config_key(producers, consumers, slots, items) 
        self.timeout       = timeout 

        # Keys have to be unique for the configs.  If I have a collision, I've done something wrong
        if self.key in configs_by_key:
            print("CONFIG __INIT__ ERROR: key for this config '%s' already in use.  Should use 'add_run' instead of init at this point" % self.key, file=sys.stderr)
            sys.exit(1)
        else:
            configs_by_key[self.key] = self

        self.name_and_key  = "%s_%s" % (name, self.key)
        self.runs          = []            # list  of runs already added to this config
        self.queue         = []            # queue of runs waiting to be added to this config
        self.total_stats   = run_stats()   # stats on the runs added to this config


    # Make the output names consistant by building from the config name and key
    # Sometimes the caller wants a run number added to name. 
    def filename(self, dir, run_num=None):
        if run_num: return "%s/%s_r%d.txt" % (dir, self.name_and_key, run_num)
        else:       return "%s/%s.txt"     % (dir, self.name_and_key)


    # Queue a run to be added later.  Note that it's a tuple so it's easy to pull the parts back off the queue.
    # If a caller has a bunch of files to process, but doesn't have them in order, then they can walk over their files,
    # handing them to an appropriate config via queue_run, then when all done, call add_queued to process them all.
    def queue_run(self, outfile, killed, graph, print_details, print_section_start):
        self.queue.append((outfile, killed, graph, print_details, print_section_start))


    # Walk the queue, adding all the queued runs.  
    def add_queued(self, print_results=True):
        for (outfile, killed, graph, print_details, print_section_start) in self.queue:
            self.add_run(outfile, killed, graph, print_details, print_section_start)
        if print_results: self.print_all_run_results()


    # Adds a run to the config, printing info about it as it works thru the analysis
    def add_run(self, outfile, killed, graph, print_details, print_section_start):
        if (print_section_start): print(SECTION_START)    # Output section start, if needed
        print("%s %s" % (label("> " + self.name + " <", colon=False), "key = %s" % self.key))
        print("%s %s" % (label("Analyzing"), outfile))
        results = run_results_object(outfile, killed, graph, print_details, print_section_start)    # Get the run results
        self.runs.append(results)                         # Append the run to the list of runs

        if print_details: 
            results.print_details(print_section_start)
        print(SECTION_END)                                # Output section break ending

        if graph: results.show_graph()                    # If the caller wants graphed, show the graph
        self.total_stats.add(results.percents)            # Add the run to the running stats total
        return results                                    # Return the analyzed run stats to the caller


    # Runs index numbers are one off, since they are logical (not zero-based)
    def return_run_percents(self, run=None):
        if run: return self.runs[run-1].percents
        else:   return self.runs[-1].percents


    # This header is used by buffer, to make it look like the thread run themselves are part of the analysis
    def print_run_header(self, overall, run):
        print(SECTION_START)
        print("%s > %s <   (run %d)" % (label("Test-%d" % overall), self.name, run))


    def print_all_run_results(self, even_one_only=False, one_liners_only=False):
        if len(self.runs) > 1 or even_one_only:
            if not one_liners_only:
                print("\n\n===========================================================================================================================================================================================")
                print("Config '%s' Summary:" % self.name)
                print("===========================================================================================================================================================================================")

            # Print the 'header' rows for the table view
            temp = "%-15s %12s %13s %13s %13s %13s %13s %8s %s" % (self.name, "Idle_Prod", "Idle_Cons","Missing","Duplicates","Invalid","OutOfOrder","", "%s" % self.key)
            temp2 = re.sub('[a-zA-Z_0-9]','-',temp)
            print(temp)
            print(temp2)
            
            test = 1
            for run in self.runs:   # Print each row
                print("%s %s       %-45s     %s"     %  (label("Test-%d" % test, -4), run.percents.one_line_summary(), run.filename, run.percents.error_notice()))
                test+=1
                
            if len(self.runs) > 1 and not one_liners_only:  # Print a Combined details if more than one row (e.g., more than one test run)
                print("--------------------------------------------------------------------------------------------------")
                print("%s" % self.total_stats.main_data_as_str())

            if not one_liners_only:
                print("===========================================================================================================================================================================================\n\n\n\n\n")




# Class to do the actual analysis of a single run
class run_results_object():
    def __init__(self, outfile, killed, graph, print_details, print_section_start):
        self.filename = outfile
        self.producers, self.consumers, self.slots, self.num_expected, self.run_num = parts_from_filename(outfile)

        # Create an internal list of the expected items.  Will be used during compares and analysis of run.
        self.expected_list = []
        for i in range(1,self.num_expected+1):
            self.expected_list.append(i)

        read_kill = self.read_file_calc_prod_cons_and_ooo()   # Does the main reading of the file, initial value setting
        self.calc_missing_dups_and_invalid()                      # After initial read, now set the missing, dups, etc.
        self.percents = run_stats(True, self.num_missing, self.num_duplicates, self.num_invalid, self.num_expected, self.ooo_count, self.items, read_kill or killed,
                            self.producers, self.num_idle_producers, self.consumers, self.num_idle_consumers)


    # Want to default 'bad' or 'missing' data to zero
    def get_part(self, parts, offset):
        try:              val = int(parts[offset])    # Can fail if offset too large, or data no a string that can be turned into an int
        except Exception: val = 0                     # On any error, just set the part to zero
        return val


    def out_of_order(self, prev, current, items):
        res = False
        if   items  <= 1:        res = False          # The first item can't be out of order       
        elif prev   <= 0:        res = False          # If the previous item was invalid (e.g., zero) or KILL (e.g., -1) do not count current as out of order, not matter what it is
        elif prev   == current:  res = False          # Duplicates should not count towards out of order
        elif prev+1 != current:  res = True           # Meaningful, different prev from current.  If current isn't 1 more, we have an ooo instance.
        return res


    def read_file_calc_prod_cons_and_ooo(self):
        killed               = False         # Note if find KILLED tuple in output
        prev                 = None          # used to help determine out of order
        self.items           = 0             # number of items found in output
        self.ooo_count       = 0             # number of out of order items

        self.x_vals          = []            # list of items for ploting
        self.y_vals          = []            # value of items for ploting
        self.output_list     = []            # list of items found in the output

        self.item_counts     = {}            # items can be duplicated, keep a count of the number of times an item is found
        self.producer_counts = {}            # keep track of the number of items produced by each producer
        self.consumer_counts = {}            # keep track of the number of items consumed by each consumer

        self.max_prod = self.producers       # We might find a producer higher than expected, get ready to capture that as we go, use later
        self.max_cons = self.consumers       # We might find a consumer higher than expected, get ready to capture that as we go, use later

        f = open(self.filename, 'r')         # open the file to analyze
        for line in f.readlines():
            parts = line.strip().split()     # The output should be a 'tuple' of  'item <tab> producer <tab> consumer'
            item  = self.get_part(parts, 0)  # item should be in first position, 0

            if item < 0:                     # buffer.py tries to capture keyboard interrupts and place a -1,-1,-1 tuple in the output if it happens.
                killed = True                # Mark this run as 'KILLED'
                continue                     # but don't add this line to the stats

            self.items += 1

            if len(parts) > 3:
                # A corrupt output line, like no file lock.  Even though there may be partially good data, including the 'item', mark the entire row as bad by setting item to 0 (e.g., invalid).
                item = 0

            prod = self.get_part(parts, 1)   # get producer.  I've run this code on previous labs, where it wasn't a tuple in the output.  So, default missing to zero.
            cons = self.get_part(parts, 2)   # get consumer.  I've run this code on previous labs, where it wasn't a tuple in the output.  So, default missing to zero.

            self.add_one(self.item_counts,     item)        # Add one to the item     counts for this 'item'
            self.add_one(self.producer_counts, prod)        # Add one to the producer counts for this 'producer'
            self.add_one(self.consumer_counts, cons)        # Add one to the consumer counts for this 'consumer'

            if prod > self.max_prod: self.max_prod = prod   # Due to command line overrides, or failures, may find a higher producer than expected.  Keep that info.
            if cons > self.max_cons: self.max_cons = cons   # Due to command line overrides, or failures, may find a higher consumer than expected.  Keep that info.

            self.output_list.append(item)    # Add item read to list
            self.x_vals.append(self.items)   # Use the number of items read to this point as the X value for plotting...
            self.y_vals.append(item)         # ... and the item itself as the Y value
            if self.out_of_order(prev, item, self.items):   # if out of order...
                self.ooo_count+=1            # update ooo count
            prev = item                      # Set prev for next time thru loop

        f.close()

        self.num_idle_producers = 0
        for p in range(1, self.max_prod+1):
            number, percentage = self.num_percent(self.producer_counts, p, self.items)  # Find count, return it and it's percent
            if number == 0: self.num_idle_producers +=1  # This producer didn't produce anything, increment the idle count

        self.num_idle_consumers = 0
        for c in range(1, self.max_cons+1):
            number, percentage = self.num_percent(self.consumer_counts, c, self.items)  # Find count, return it and it's percent
            if number == 0: self.num_idle_consumers +=1  # This consumer didn't consumer anything, increment the idle count

        return killed


    def add_one(self, a_dict, key):
        try:              a_dict[key] += 1   # Add one to the ongoing count, if the key already present
        except Exception: a_dict[key]  = 1   # Otherwise, set value at key to one.


    # Using expected_list, determine what's missing or duplicated in the output
    def calc_missing_dups_and_invalid(self):
        self.missing_items   = []
        self.duplicate_items = {}
        self.num_duplicates  = 0

        for item in self.expected_list:
            if not item in self.output_list:
                self.missing_items.append(item)
            else:
                # Item found in the output, but it may have been there more than once
                count = self.item_counts[item]
                if count > 1:
                    self.duplicate_items[item]  = count              # Record as a duplicate, storing how many times the item appeared in the output
                    self.num_duplicates        += count - 1          # Tally the ongoing dup count.  Note that one of the instances is not a dup (e.g., first one was 'good')
        self.num_missing = len(self.missing_items)                   # Handy reference count, could have just done len() everytime

        # Now, check for data that's 'wrong' and shouldn't have been in the output
        self.invalid_items = {}
        self.num_invalid   = 0
        for item in self.output_list:
            if (not item in self.expected_list) and (not item in self.invalid_items):    # This item is invalid, and hasn't been recorded as such yet
                count = self.item_counts[item]                       # Get the number of instances of this item
                self.invalid_items[item] = count                     # Record the item as invalid, storing how many times the item appeared in the output
                self.num_invalid += count                            # Add to the ongoing, overall, invalid count
            

    # Driver function to make printing out the details easier to follow and update
    def print_details(self, print_section_start):
        print("%s MaxPro=%d, MaxCon=%d, Slots=%d, Items=%d (Run=%d)" % (label("File parms found"), self.max_prod, self.max_cons, self.slots, self.num_expected, self.run_num))
        if self.percents.killed.percent > 0:
            print("Partial data, run terminated.")
        print("--------------------------------------------------------------------------------------------------")
        print("%s %s" % (label("Missing List"),    self.missing_items))        # Outputs the Missing LIST
        print("--------------------------------------------------------------------------------------------------")
        print("%s %s" % (label("Duplicates List"), self.duplicate_items))      # Outputs the Duplicates LIST
        print("--------------------------------------------------------------------------------------------------")
        print("%s %s" % (label("Invalid List"),    self.invalid_items))        # Outputs the Invalid LIST
        print("--------------------------------------------------------------------------------------------------")
        self.print_prod_activity(print_section_start)                          # Outputs the producer idle %'s
        print("--------------------------------------------------------------------------------------------------")
        self.print_cons_activity(print_section_start)                          # Outputs the consumer idle %'s 
        print("--------------------------------------------------------------------------------------------------")
        print("%s" % self.percents.main_data_as_str(self.num_expected))        # Outputs %'s for missing, dup, invalid, and ooo 


    # Want to return a raw number from a dictionary, and turn it into percent
    def num_percent(self, a_dict, key, base):
        try:              number  = a_dict[key]           # Find the key's value
        except Exception: number  = 0                     # If not there, assume zero
        return number, percent(number, base)              # return number found (or zero), and corresponding percent


    # Print the producer stats, flagging idle producers, which could be an error
    def print_prod_activity(self, print_section_start):
        for p in range(1, self.max_prod+1):
            number, percentage = self.num_percent(self.producer_counts, p, self.items)  # Find count, return it and it's percent
            print("%s %6.2f%% %s" % (label("producer-%d" % p), percentage, (idle_prod_error if number==0 else "")))


    # Print the consumer stats, flagging idle consumers, which could be an error
    def print_cons_activity(self, print_section_start):
        for c in range(1, self.max_cons+1):
            number, percentage = self.num_percent(self.consumer_counts, c, self.items)  # Find count, return it and it's percent
            print("%s %6.2f%% %s" % (label("consumer-%d" % c), percentage, (idle_cons_error if number==0 else "")))


    # Using matlibplot, show a graph of the result to help visualize out of order
    def show_graph(self):
        if self.percents.error():            run_error   = "Errors:  "
        else:                                run_error   = ""

        if self.percents.killed.percent > 0: kill_string = "  KILLED  "
        else:                                kill_string = ""

        try:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots()             # Create a figure containing a single axes.
            plot_title = "Run%d, Prod=%d, Cons=%d, Slots=%d, Items=%d (%s)\n%s%s%s" % (self.run_num, self.max_prod, self.max_cons, self.slots, self.num_expected, pathlib.Path.cwd().name, run_error, kill_string, self.percents.subtitle_summary())
            plt.title(plot_title)                # set title
            plt.plot(self.x_vals, self.y_vals)   # Use the data built up during the analysis
            plt.show()                           # Now... call to display 

        except Exception as err:
            print("\n   >>>   WARNING:  Could not produce matplotlib graphs in this environment.               <<<")
            print(  "   >>>             Install matplotlib per instructions in lab write-up,                   <<<")
            print(  "   >>>             then re-run or call analyze directly via something like:               <<<")
            print(  "   >>>             %-70s <<<\n" % ("python3 buffer.py -m -A %s" % self.filename))
            print(  "   >>>   Actual system error message: ", err, file=sys.stderr)



# Convenience class to help build a single running count, base, and percent
# Will also be used to accumulate corresponding stat across runs
class a_stat:
    def __init__(self, count=0, base=0):
        if base: self.runs = 1                           # A Stat is either associated with a given run, or a collection of runs.  This is triggered off 'base' during init.  
        else:    self.runs = 0                           # If base was zero, this is going to be a collection of runs.

        self.count   = count                             # Count is the 'instances' of whatever we're interested in for this run or set of runs.
        self.base    = base                              # Base  is the 'base'  to use when we want to turn 'count' into a percent
        self.percent = percent(self.count, self.base)    # Build the percent

    def add(self, other):                                # Want to add in stats from another run, or set of runs
        self.runs  += other.runs                         # Add the number of runs together
        self.count += other.count                        # Add the counts together
        self.base  += other.base                         # Add the bases  together
        self.percent = percent(self.count, self.base)    # Construct new percent


# Convenience class to help maintain and print a set of stats about a run, each statistic primarily being a_stat class instance
# Will also be used to accumulate corresponding info across runs
class run_stats:
    def __init__(self, set_clean=False, num_missing=0, num_duplicates=0, num_invalid=0, num_expected=0, ooo_order=0, output_items=0, killed=False, producers=0, idle_producers=0, consumers=0, idle_consumers=0):
        self.missing          = a_stat(num_missing,             num_expected)       # Stats on the number of missing      items   (this init works with base = anything, even zero)
        self.duplicates       = a_stat(num_duplicates,          num_expected)       # Stats on the number of duplicate    items   (this init works with base = anything, even zero)
        self.invalid          = a_stat(num_invalid,             num_expected)       # Stats on the number of invalid      items   (this init works with base = anything, even zero)
        self.ooo              = a_stat(ooo_order,               output_items)       # Stats on the number of out of order items   (this init works with base = anything, even zero)
        self.idle_producers   = a_stat(idle_producers,          producers)          # Stats on the number of idle producers       (this init works with base = anything, even zero)
        self.idle_consumers   = a_stat(idle_consumers,          consumers)          # Stats on the number of idle producers       (this init works with base = anything, even zero)

        # There are a couple of stats that have to be set closely, only looking at non-zero info, or hand setting to zero
        if set_clean:                                                               # If set_clean, then initializing for 1 run (e.g, base = 1)
            self.killed       = a_stat(int(killed),              1)                 # Stats on the number of killed runs, with base 1
            self.clean_runs   = a_stat(int(not(self.error())),   1)                 # Stats on the number of clean runs,  with base 1
            self.ooo_not_zero = a_stat(int(self.ooo.percent!=0), 1)                 # Stats on the number of runs with OOO!=0, with base 1
        else:                                                                       # set_clean=False, so initialize as an object that will accumulate info later, thus base = 0
            self.killed       = a_stat()                                            # Stats on the number of killed runs, with base 0      (e.g., nothing yet)
            self.clean_runs   = a_stat()                                            # Stats on the number of clean runs,  with base 0      (e.g., nothing yet)
            self.ooo_not_zero = a_stat()                                            # Stats on the number of runs with OOO!=0, with base 0 (e.g., nothing yet)


    # Add the 'other' set of stats to this one.  Each is a simple call to 'add' for the corresponding 'a_stat' items
    def add(self, other):
        self.missing.add(        other.missing)
        self.duplicates.add(     other.duplicates)
        self.invalid.add(        other.invalid)
        self.ooo.add(            other.ooo)
        self.ooo_not_zero.add(   other.ooo_not_zero)
        self.idle_producers.add( other.idle_producers)
        self.idle_consumers.add( other.idle_consumers)
        self.killed.add(         other.killed)
        self.clean_runs.add(     other.clean_runs)


    # Want a logical view of a non-clean run (e.g., a run with an error)
    def error(self):
        return (self.idle_producers.percent != 0 or         # There can be no idle producer threads
                self.idle_consumers.percent != 0 or         # There can be no idle consumer threads
                self.missing.percent         > 0 or         # There can be no missing   items
                self.duplicates.percent      > 0 or         # There can be no duplicate items
                self.invalid.percent         > 0 or         # There can be no invalid   items
                self.ooo.percent            == 0 or         # OOO cannot be zero.  (Will check for average targets across configs, as opposed to a single config)
                self.killed.percent          > 0)           # There can be no killed runs


    # Want to have standard text flagging online summaries
    def error_notice(self):
        temp = ""
        if self.error():   temp += error_star
        if self.killed.percent > 0: temp += kill_notice
        return  temp


    # A 'simple' one line summary of a run, or set of runs.  
    def one_line_summary(self):
        format_num = "%10.2f%%"                                      # Base way to format the output, where each a_stat is going to focus on its percent
        format_err = format_num  + " * "                             # Add a '*' to percent outputs that are errors
        format_low = format_num  + " L "                             # Add a 'L' to ooo percent outputs that are below the target ooo
        dash_zero  = "%10s    "  % "-"                               # Where possible, change a zero, which is not an error, to a simple '-' so errors elsewhere jump out more
        good_ooo   = "%10s   "   % (format_num % self.ooo.percent)   # OOO is special.  Zero is it's error.  So, a positive value is not an error.

        temp  = format_err  %  self.idle_producers.percent  if self.idle_producers.percent > 0 else dash_zero
        temp += format_err  %  self.idle_consumers.percent  if self.idle_consumers.percent > 0 else dash_zero
        temp += format_err  %  self.missing.percent         if self.missing.percent        > 0 else dash_zero
        temp += format_err  %  self.duplicates.percent      if self.duplicates.percent     > 0 else dash_zero
        temp += format_err  %  self.invalid.percent         if self.invalid.percent        > 0 else dash_zero

        if   self.ooo.percent == 0:           temp += format_err  %  self.ooo.percent    # OOO zero is an error
        elif self.ooo.percent  < TARGET_OOO:  temp += format_low  %  self.ooo.percent    # OOO below target is a warning
        else:                                 temp += good_ooo                           # OOO otherwise is good, and still needs put out, instead of a -

        return temp
        

    # Want a short, meaningful subtitle that contains run stats for the matlibplot graphs
    def subtitle_summary(self):
        format_str = "%s%s=%0.0f%%   " # Consistent format with space to precede Key=Value with a '*' if there's an error.
        temp  = format_str % ("*" if self.missing.percent    > 0 else " ", "Missing", self.missing.percent)
        temp += format_str % ("*" if self.duplicates.percent > 0 else " ", "Dup",     self.duplicates.percent)
        temp += format_str % ("*" if self.invalid.percent    > 0 else " ", "Invalid", self.invalid.percent)
        temp += format_str % (                                        " ", "OOO",     self.ooo.percent)
        return temp


    # Want a string (that will be printed in context) that contains gory details about the run(s)
    def main_data_as_str(self, num_expected=-1, ooo_msg=ooo_target_warn):
        temp        = ""
        delta       = -4
        format_str1 = "%11.2f%%   %s  %s"
        format_str2 = format_str1     + "\n"
        format_str3 = "      %-5s  %s"
        format_str4 = format_str3  + "\n"

        # Notice that the errors per stat have been customized at the far end of the lines below.  The parts that start like... '(error_zero  if self' 
        if num_expected>=0:   # Have something expected, can show meaningful stats
            temp += label("Num Expected",     delta) + "%8d\n"     % num_expected
        temp     += label("Missing Items",    delta) + format_str2 % (self.missing.percent,         self.format_count_of_base_string(self.missing),        (error_zero            if self.missing.percent         > 0   else ""))
        temp     += label("Duplicates",       delta) + format_str2 % (self.duplicates.percent,      self.format_count_of_base_string(self.duplicates),     (error_zero            if self.duplicates.percent      > 0   else ""))
        temp     += label("Invalid",          delta) + format_str2 % (self.invalid.percent,         self.format_count_of_base_string(self.invalid),        (error_zero            if self.invalid.percent         > 0   else ""))
        temp     += label("Idle Producers",   delta) + format_str2 % (self.idle_producers.percent,  self.format_count_of_base_string(self.idle_producers), (error_zero            if self.idle_producers.percent        else ""))
        temp     += label("Idle Consumers",   delta) + format_str2 % (self.idle_consumers.percent,  self.format_count_of_base_string(self.idle_consumers), (error_zero            if self.idle_consumers.percent        else ""))
        temp     += label("OOO Average",      delta) + format_str2 % (self.ooo.percent,             self.format_count_of_base_string(self.ooo),            (ooo_msg % TARGET_OOO  if self.ooo.percent < TARGET_OOO      else ""))
        temp     += label("OOO Not Zero",     delta) + format_str2 % (self.ooo_not_zero.percent,    self.format_count_of_base_string(self.ooo_not_zero),   (error_hundred         if self.ooo_not_zero.percent   != 100 else ""))

        # Want the KILL output customized based on number of runs, so it's easier for people to read in context
        temp1     = label("Test Killed",      delta) + format_str4 % (self.killed.percent > 0,                                                              error_false           if self.killed.percent          > 0   else " ")
        temp2     = label("Killed Tests",     delta) + format_str2 % (self.killed.percent,  self.format_count_of_base_string(self.killed),                 (error_zero            if self.killed.percent          > 0   else ""))

        # Want the CLEAN output customized based on number of runs, so it's easier for people to read in context
        temp3     = label("Clean Test",       delta) + format_str3 % (self.clean_runs.percent == 100,                                                       error_true            if self.clean_runs.percent     != 100 else "")
        temp4     = label("Clean Tests",      delta) + format_str1 % (self.clean_runs.percent,self.format_count_of_base_string(self.clean_runs),           (error_hundred         if self.clean_runs.percent     != 100 else ""))

        # Num of runs in killed and clean should be the same, can just use killed.runs to pick right strings for both
        if self.killed.runs == 1:  temp += temp1 + temp3
        else:                      temp += temp2 + temp4

        return temp



    # Want to automatically put out a meaning evaluation of a set of runs across multiple configurations
    def print_sample_score(self):

        ooo_factor = 100 / TARGET_OOO     # Will use OOO target to adjust the actual OOO average to 'scale' to a possible 100% score on the OOO portion

        avail = 0                         # Running amount of available points
        total = 0                         # Running total of points achieved

        print("\n\n\n\n** SAMPLE ***  Grade of the analyzed test runs in %s:" % pathlib.Path.cwd().name)
        print("---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------")
        if self.clean_runs.base == 0:
            print("No runs to grade.")
        else:

            # Note the 'flip' variable.  Tells me if the value should be inverted to make a 'perfect' score 100% on that facet as compared to the original data.
            for (l, b, p, flip, all_or_nothing, extra) in (
                    ("Not  Missing",                 10,     self.missing.percent,            1, 0, "         ::::       100%%  -   Percent Missing                                         =       100%%  - %7.2f%%    =   %6.2f%%" % (self.missing.percent,           100-self.missing.percent)),
                    ("Not  Duplicate",               10,     self.duplicates.percent,         1, 0, "         ::::       100%%  -   Percent Duplicates                                      =       100%%  - %7.2f%%    =   %6.2f%%" % (self.duplicates.percent,        (0 if 100-self.duplicates.percent<0 else 100-self.duplicates.percent))),
                    ("Not  Invalid",                 10,     self.invalid.percent,            1, 0, "         ::::       100%%  -   Percent Invalid                                         =       100%%  - %7.2f%%    =   %6.2f%%" % (self.invalid.percent,           (0 if 100-self.invalid.percent<0    else 100-self.invalid.percent))),
                    ("Busy Producers",                5,     self.idle_producers.percent,     1, 0, "         ::::       100%%  -   Percent Idle Producers                                  =       100%%  - %7.2f%%    =   %6.2f%%" % (self.idle_producers.percent,    100-self.idle_producers.percent)),
                    ("Busy Consumers",                5,     self.idle_consumers.percent,     1, 0, "         ::::       100%%  -   Percent Idle Consumers                                  =       100%%  - %7.2f%%    =   %6.2f%%" % (self.idle_consumers.percent,    100-self.idle_consumers.percent)),
                    ("OOO  >= %.1f%%" % TARGET_OOO,  10,     self.ooo.percent * ooo_factor,   0, 0, "         ::::       min(100%%, OOO_Ave / OOO_Target)   =   min(100%%, %6.2f / %5.1f)   =   min(100%%,   %7.2f%%)   =   %6.2f%%" % (self.ooo.percent, TARGET_OOO,   100*(self.ooo.percent / TARGET_OOO), 100*min(1, (self.ooo.percent / TARGET_OOO)))),
                    ("OOO  Not Zero",                10,     self.ooo_not_zero.percent,       0, 0, ""),
                    (None, None, None, None, None, None),
                    ("No   Missing Items",           10,     self.missing.percent,            1, 1, ""),
                    ("No   Duplicates",              10,     self.duplicates.percent,         1, 1, ""),
                    ("No   Invalid Items",           10,     self.invalid.percent,            1, 1, ""),
                    ("No   Tests Killed",            10,     self.killed.percent,             1, 1, "")):

                if not l:
                    print("-------------------------------------------------------")
                
                else:

                    if flip: percent = 1 - p/100          # Flip values if need to invert
                    else:    percent =     p/100          # Otherwise, use as-is, just converting back to it's real number

                    if percent < 0: percent = 0           # Scaling, rounding, flipping, or 'really bad' runs could have these outside ot ranges.  Don't go below zero. 
                    if percent > 1: percent = 1           # Don't go above 1 (e.g., 100%)

                    if all_or_nothing:
                        if percent < 1:
                            percent = 0
                        print("%s %7s   ( %6.3f of %3d points )   %s" % (label(l, num=20), (True if percent else False), b*percent, b, extra))
                    else:
                        print("%s %6.2f%%   ( %6.3f of %3d points )   %s" % (label(l, num=20), percent*100, b*percent, b, extra))
                    avail += b                            # Add this base, to running available
                    total += b*percent                    # Add the percent of this base earned to the ongoing total achieved.

        print("=======================================================")
        print("%s %18.3f of %3d points"  % (label("Total"), total, avail))
        print("%s %17.2f  of %3d points              ::::       Rubric 'GRADE Run' entry would be:  -%.2f " % (label("Carmen 'Round'"), total, avail, avail-total))   # Carmen rounds, so show this, and have it handy for putting in our spreadsheets
        print("---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------")

        

    # Want consistent information in lines that includes a '( x / y )' string in detail lines to show the numbers, not just the %'s
    def format_count_of_base_string(self, stat, pad=0):
        # First, figure out out the largest numerator and demoninator so I can line everything up
        max_count = max([self.idle_producers.count, self.idle_consumers.count, self.missing.count, self.duplicates.count, self.invalid.count, self.ooo.count, self.ooo_not_zero.count, self.killed.count])        
        max_base  = max([self.idle_producers.base,  self.idle_consumers.base,  self.missing.base,  self.duplicates.base,  self.invalid.base,  self.ooo.base,  self.ooo_not_zero.base, self.killed.base])

        count_len = len("%d" % max_count) + pad                     # Turn largest numerator   into a string, then figure out it's length
        base_len  = len("%d" % max_base)  + pad                     # Turn largest denominator into a string, then figure out it's length

        format_str = "( %%%dd / %%%dd )" % (count_len, base_len)    # This is the key line.  Use the longest len of numerator and denominator to generate a format string
        return       format_str % (stat.count, stat.base)           # Now, use the format string to construct the a_stat info requested




# Given a list of configurations, print summaries for each and combine for an overall result, printing overall grade.
# Note: This only prints the Summary and Results of each config if there's more than one config in a_list because this function is called from some 
# places where printing the summary after a single config just doesn't make sense, cluttering the output with duplicate info.  
# But, to keep the caller code simple, putting the check here for the number of things being processed.

def print_summaries_and_grade(a_list, grade):
    overall_stats = run_stats()                          # Create overall stats
    num = len(a_list)                                    # if there's just one config passed in, will limit prints to avoid printing info that's already been output during the processing that just took place.

    if num > 1:                                          # Have multiple configs to process, need to put out summary header
        print("\n\n\n\nv-v-v-v-v-v-v-v-v-v-v-v-v-v       Config One-Line Summaries       v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v\n\n")

    for c in a_list:
        if type(c) == config_object: config = c          # Input might not be a list of things, could essentially be just one config
        else:                        config = a_list[c]  # Input was a list-like object, extract the config 'c' from it

        if num > 1:                                      # Have multiple configs to process, need to put out summary one-liners
            config.print_all_run_results(True, True)     # Have this config print out each one-liner for its runs
            print("\n")                                  # Separate the config one-liners

        overall_stats.add(config.total_stats)            # Add this config info to overall stats

    if num > 1:                                          # Have multiple configs to process, need to put out overall header and overall details
        print("\n\n\n\nv-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v        Overall Results        v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v-v\n")
        print("%s" % overall_stats.main_data_as_str(ooo_msg=ooo_target_error))  

    overall_stats.print_sample_score()                   # Output the overall grade



   
# Each line should have this format, with data separated by whitespace:
# Name   Producers   Consumers   Slots   Items   Timeout(in seconds)
#
# Grade-Sample01    3   1    7    57   1

def read_configs_from_file(grade_file):
    try:
        g_file  = open(grade_file, 'r')                         # open grade config file
    except Exception as err:
        print("\nERROR: Invalid grade configuration file name '%s'\n" % grade_file, file=sys.stderr)
        print("Actual system error message: ", err, file=sys.stderr)
        sys.exit(1)

    configs = []                                                # set configs to empty
    i       = 0                                                 # Want to count put out error messages by line number
    for line in g_file.readlines():                             # Read each line from the file
        i += 1                                                  # Increment line number
        if line.startswith('#'):                                # Ignore comment lines
            continue

        parts = line.strip().split()                            # strip whitespace from ends of line, and then split on internal whitespace
        if len(parts) == 0:                                     # Ignore 'blank' lines (e.g., parts == 0)
            continue

        if len(parts) < 6:                                      # Non-blank line, but doesn't have required 6 parts.
            print("\nERROR: invalid GRADE config.  Need 6 parts.  See line %d: '%s'\n" % (i, line.strip()), file=sys.stderr)
            sys.exit(1)                                         # If not at least 6 parts, exit with error

        # Have 6 parts, but they not be 'good'
        name  = parts[0]                                        # Name will get checked as valid as part of config_object creation
        try:                                                    # Assume any 'int' is good, though really, should be doing some 'logical' check on them.
            producers = int(parts[1])                           # Maybe I'll add that to the config_object init at some point...
            consumers = int(parts[2])                     
            slots     = int(parts[3])                     
            items     = int(parts[4]) 
            timeout   = int(parts[5])
        except Exception as err:   
            print("\nERROR: Bad data in GRADE file.  See line %d: '%s'" % (i, line.strip()))
            print("       Make sure these are all integers: Producer='%s', Consumer='%s', Slots='%s', Items='%s', and Timeout='%s'.\n" % (parts[1], parts[2], parts[3], parts[4], parts[5]))
            print("Actual system error message: ", err, file=sys.stderr)
            sys.exit(1)

        # Use input line as parms to config_object, adding returned object to list of configs
        configs.append(analyze.config_object(name, producers, consumers, slots, items, timeout))  
            
    return configs  
