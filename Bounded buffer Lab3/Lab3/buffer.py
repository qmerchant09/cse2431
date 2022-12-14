import threading
import sys
import os
import argparse
import pathlib
import importlib
import analyze
import student
import time
import glob
import secrets
import multiprocessing

try:
    analyze.TARGET_OOO = min(40, 4.5 * multiprocessing.cpu_count())  # Cap this at 40%, but try to factor in the VCPU
except Exception:
    analyze.TARGET_OOO = 10                                          # Set to 10%, if call to find VCPU failed

orig_target = analyze.TARGET_OOO

# Convenience class for buffer related info, so it can be passed into functions all at once
class buffer_object:
    def __init__(self, slots):
        self.IN               = 0                         # Initialize IN and OUT to zero (e.g., they are equal, so the buffer is initially empty)
        self.OUT              = 0                         # Initialize IN and OUT to zero (e.g., they are equal, so the buffer is initially empty)
        self.KILL             = False                     # Variable to pass in user keyboard interrupts to help terminate the producer/consumer loops.  
        self.PRODUCERS_DONE   = False                     # Denotes producer THREADS are done.  This is set by the wrapper code.  Student code should NOT set this, but it should CHECK it in the consumer function to break out of the 'while' loop.
        self.CONSUMERS_DONE   = False                     # Denotes consumer THREADS are done.  This is set by the wrapper code.  Student code should NOT set or use this.  The wrapper code uses it to check timeouts and set buffer.KILL
        self.NUM_SLOTS        = slots                     # Prescribed logical size of buffer
        self.ITEMS            = [0] * slots               # Initialize the data item array to the right size


# Convenience class for locks, so they can be passed into functions all at once
class locks_object:
    def __init__(self):
        self.producer_file_in   = threading.Lock()        # producer lock for INPUT_FILE  access
        self.consumer_file_out  = threading.Lock()        # consumer lock for OUTPUT_FILE access

        self.producer_buffer    = threading.Lock()        # producer lock for buffer access
        self.consumer_buffer    = threading.Lock()        # consumer lock for buffer access



# Setup defaults and parse command line arguments.

DEFAULT_PRODUCERS    = 3            # Default number of producer threads
DEFAULT_CONSUMERS    = 1            # Default number of consumer threads
DEFAULT_BUFFER_SLOTS = 10           # Default size of buffer
DEFAULT_INPUT_LINES  = 100          # Default length of file INPUT_FILE to create
DEFAULT_RUNS         = 1            # Default number of runs per config
DEFAULT_TIMEOUT      = 2            # Default number of seconds to let a test run before trying to kill
DEFAULT_GLOB         = "output/*"   # As a default, analyze all the files in the output directory if called for analysis only
DEFAULT_CONFIG_NAME  = "CMD-LINE"   # Set default config name to show that it came from the command line, instead of the GRADE array.  User can override.
DEFAULT_GRADE_FILE   = "sample_grade_configs.txt"   # File with sample grade configs for testing
ANALYZE_HELP         ="""Glob style string of files to analyze.  Be sure to quote the string so your shell doesn't
expand it into a list (e.g., -A 'output/*p3*').    [ Default: None

-----------------------------------------------------------------------------------------
 """



parser = argparse.ArgumentParser(description=" \nBounded buffer implementation for OSU 2431 SP21.\n ", formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, width=200))
parser.add_argument("-p", "--producers",    type=int,   default=DEFAULT_PRODUCERS,     metavar = "#",   help="Number of producer threads                         [ Default:   %3d" % DEFAULT_PRODUCERS)
parser.add_argument("-c", "--consumers",    type=int,   default=DEFAULT_CONSUMERS,     metavar = "#",   help="Number of consumer threads                         [ Default:   %3d" % DEFAULT_CONSUMERS)
parser.add_argument("-s", "--slots",        type=int,   default=DEFAULT_BUFFER_SLOTS,  metavar = "#",   help="Number of buffer slots                             [ Default:   %3d" % DEFAULT_BUFFER_SLOTS)
parser.add_argument("-i", "--items",        type=int,   default=DEFAULT_INPUT_LINES,   metavar = "#",   help="Number of items initially placed in input.txt      [ Default:   %3d" % DEFAULT_INPUT_LINES)
parser.add_argument("-r", "--runs",         type=int,   default=DEFAULT_RUNS,          metavar = "#",   help="Number of times to run each configuration          [ Default:   %3d" % DEFAULT_RUNS)
parser.add_argument("-t", "--timeout",      type=float, default=DEFAULT_TIMEOUT,       metavar = "#",   help="Number of seconds before buffer.KILL is set        [ Default:   %3d" % DEFAULT_TIMEOUT)
parser.add_argument("-n", "--name",         type=str,   default=DEFAULT_CONFIG_NAME,   metavar = "s",   help="Name for config being run from command line        [ Default: '%s'"  % DEFAULT_CONFIG_NAME)
parser.add_argument("-o", "--outOfOrder",   type=int,   default=analyze.TARGET_OOO,    metavar = "#",   help="Target Out of Order percent                        [ Default:   %3d" % analyze.TARGET_OOO)
parser.add_argument("-m", "--matplot",                  action="store_true",                            help="Show matplotlib graph                              [ Default: False\n\n ")

parser.add_argument("-g", "--grade",                    action="store_true",                            help="Shorthand for -G '%s'        [ Default: False" % DEFAULT_GRADE_FILE)
parser.add_argument("-G", "--GradeFile",    type=str,   default=None,                  metavar = "s",   help="Run 'GRADE' configurations found in filename 's'   [ Default: None\n\n ")

parser.add_argument("-a", "--analyze",                  action="store_true",                            help="Shorthand for -A 'output/*'                        [ Default: False")
parser.add_argument("-A", "--AnalyzeFile",  type=str,   default=None,                  metavar = "s",   help=ANALYZE_HELP)

parser.add_argument("-l", "--list",                     action="store_true",                            help="List available teacher functions                   [ Requires access to teacher.py")
parser.add_argument("-x", "--tproducer",    type=int,   default=None,                  metavar = "#",   help="Use version # of teacher producer code             [ Requires access to teacher.py")
parser.add_argument("-y", "--tconsumer",    type=int,   default=None,                  metavar = "#",   help="Use version # of teacher consumer code             [ Requires access to teacher.py")
parser.add_argument("-z", "--tboth",        type=int,   default=None,                  metavar = "#",   help="Shorthand for  -x# -y#                             [ Requires access to teacher.py\n ")

args   = parser.parse_args()


# Update target with any command line input
if args.outOfOrder <= 0 or args.outOfOrder > 100:
    print("\nERROR: Parameter -o (--outOfOrder) value must be greater than 0 and less than or equal to 100.  Input was %d.\n" % args.outOfOrder, file=sys.stderr)
    sys.exit(1)
analyze.TARGET_OOO = args.outOfOrder


# If -a or -A flag set, just do analysis on specified previous run output, then exit
if args.analyze or args.AnalyzeFile:
    if args.AnalyzeFile: input_glob = args.AnalyzeFile                        # if -A parm set, use it for input glob
    else:                input_glob = DEFAULT_GLOB                            # otherwise, use default glob as a convenience

    for filename in sorted(glob.glob(input_glob)):
        config = analyze.config_from_filename(filename, args.timeout)         # Find the config that should manage this run, based on the filename
        config.queue_run(filename, False, args.matplot, True, True)           # Queue the run in that config for analyzing once we have all the filenames assigned to configs

    for key in sorted(analyze.configs_by_key):
        analyze.configs_by_key[key].add_queued()                              # Tell each config to process and print the queued runs.
    analyze.print_summaries_and_grade(analyze.configs_by_key, args.grade)     # Reprint the summaries (if needed, since there could have been a ton of info fly by when analyzing a bunch of files) and the grade

    print("\n\nUsed Target OOO = %5.2f%%.  %60s" % (analyze.TARGET_OOO, "" if orig_target != args.outOfOrder else "(You can override this target via the -o parameter.)"))
    print("Program Use Terminated -- Analysis Only.  (Run in directory '%s')\n" % pathlib.Path.cwd().name)
    sys.exit()



# -g and -G not set, build a single config from parm (and/or their defaults)
if not args.grade and not args.GradeFile:                       
    configs = [analyze.config_object(args.name, args.producers, args.consumers, args.slots, args.items, args.timeout)]

else: # -g or -G flag set, find file and use as Grade configurations
    if args.GradeFile: grade_file = args.GradeFile        # if -G parm set, use it for grade config input
    else:              grade_file = DEFAULT_GRADE_FILE    # otherwise, use default grade file 
    configs = analyze.read_configs_from_file(grade_file) 


p_target = student.student_producer   # set default producer function
c_target = student.student_consumer   # set default consumer function

# Manage override of producer/consumer function
if args.list or args.tproducer or args.tconsumer or args.tboth:
    try:   import teacher
    except Exception as err:
        print("\nERROR: You must have access to the file 'teacher.py' to run this part of the lab.\n", file=sys.stderr)
        print("Actual system error message: ", err, file=sys.stderr)
        sys.exit(1)

    # List the registered teacher functions 
    if args.list:
        teacher.list_functions()
        sys.exit()

    # Set both
    if args.tboth:
        args.tproducer = args.tboth
        args.tconsumer = args.tboth

    if args.tproducer: p_target = teacher.which_teacher_producer(args.tproducer)    # register appropriate function, if set
    if args.tconsumer: c_target = teacher.which_teacher_consumer(args.tconsumer)    # register appropriate function, if set



# Sets KILL to True in buffer, and writes 3-part 'tuple' to OUTPUT_FILE to show KILL happened
def kill_buffer(a_buffer, f_out):
    a_buffer.KILL = True
    try:
        f_out.write('%d\t%d\t%d\n' % (-1, -1, -1))                          
        f_out.flush()  
    except Exception as err:
        print("\nERROR: Failed to cleanly write KILL tuple to file.  Grade for this run may be inflated.\n", file=sys.stderr)
        print("Actual system error message: ", err, file=sys.stderr)



# Timer function to try to kill off threads that are looping too long
def timer_thread(seconds, f_out, a_buffer, locks):
    time.sleep(seconds)
    if not a_buffer.PRODUCERS_DONE or not a_buffer.CONSUMERS_DONE:
        # Only set KILL if there are producer or consumer threads still running
        print("%s %s" % (analyze.label("Timer"), "Expired.  Setting buffer.KILL=True to stop threads and marking run as killed.  If threads don't gracefully stop, enter Control-C to forcefully stop them."))
        kill_buffer(a_buffer, f_out)
    


overall_test_num = 1                                          # Variable to keep track of the overall number of tests run during this program invocation

INPUT_DIR  = 'input'                                          # Default input  directory name
OUTPUT_DIR = 'output'                                         # Default output directory name

if not os.path.exists(INPUT_DIR):  os.makedirs(INPUT_DIR)     # Create the input  directory, if not present
if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)    # Create the output directory, if not present


# Loop over each configuration, running each 
for config in configs:

    INPUT_FILE = config.filename(INPUT_DIR)                   # Get appropriate input filename for config
    f          = open(INPUT_FILE, 'w')                        # Create the input file
    for i in range(1, config.items+1):                        # For requested size...
        f.write("%d\n" % i)                                   #    put out each 'item'
    f.close()                                                 # Close the created input file.

    for run in range(1, args.runs+1):                         # Execute this configuration the requested number of times
        aBuffer = buffer_object(config.slots)                 # Create a new buffer for each run, to avoid bad spill-over info
        locks   = locks_object()                              # Create new locks for each run, to avoid spill-over

        config.print_run_header(overall_test_num, run)        # Print the header, so the 'running' messages appear as part of the analysis
        overall_test_num += 1                                 # Increment overall test count, which is different than runs since multiple configs could be executed
        OUTPUT_FILE = config.filename(OUTPUT_DIR, run)        # Get appropriate output file for config

        try:
            producer_threads   = []                           # list to help manage producer threads for this run
            consumer_threads   = []                           # list to help manage consumer threads for this run

            f_in  = open(INPUT_FILE,  'r')                    # Open   READ  input  file handle
            f_out = open(OUTPUT_FILE, 'w')                    # Create WRITE output file handle
        
            if run % 2:                                       # On Odd numbered runs, start producer first
                print("%s Starting %d producers using '%s' ..." % (analyze.label("Threads"), config.producers, p_target.__name__))
                for x in range(config.producers):             # Create producer threads, have them run the 'producer' function
                    thread = threading.Thread(target=p_target, args=(x+1,f_in,aBuffer,locks), name="Producer-%d" % (x+1))           # Setup thread, function, args, and name
                    producer_threads.append(thread)           # Add new thread to producer_threads list                                              
                    thread.start()                            # Start the new producer thread
                
                print("%s Starting %d consumers using '%s' ..." % (analyze.label("Threads"), config.consumers, c_target.__name__))
                for x in range(config.consumers):             # Create consumer threads, have them run the 'consumer' function
                    thread = threading.Thread(target=c_target, args=(x+1,f_out,aBuffer,locks), name="Consumer-%d" % (x+1))          # Setup thread, function, args, and name
                    consumer_threads.append(thread)           # Add new thread to consumer_threads list                                
                    thread.start()                            # Start the new consumer thread
            
            else:                                             # On Even numbered runs, start consumer first
                print("%s Starting %d consumers using '%s' ..." % (analyze.label("Threads"), config.consumers, c_target.__name__))
                for x in range(config.consumers):             # Create consumer threads, have them run the 'consumer' function
                    thread = threading.Thread(target=c_target, args=(x+1,f_out,aBuffer,locks), name="Consumer-%d" % (x+1))          # Setup thread, function, args, and name
                    consumer_threads.append(thread)           # Add new thread to consumer_threads list                                
                    thread.start()                            # Start the new consumer thread

                print("%s Starting %d producers using '%s' ..." % (analyze.label("Threads"), config.producers, p_target.__name__))
                for x in range(config.producers):             # Create producer threads, have them run the 'producer' function
                    thread = threading.Thread(target=p_target, args=(x+1,f_in,aBuffer,locks), name="Producer-%d" % (x+1))           # Setup thread, function, args, and name
                    producer_threads.append(thread)           # Add new thread to producer_threads list                                              
                    thread.start()                            # Start the new producer thread
                



            thread = threading.Thread(target=timer_thread, args=(config.timeout,f_out,aBuffer,locks), name="Timer", daemon=True) # Setup timer thread, function, args, and name
            thread.start()                                    # Start the new timer    thread

            for p in producer_threads: p.join()               # Wait for each individual producer threads
            aBuffer.PRODUCERS_DONE = True                     # Let consumer threads know the producer threads are done
            print("%s Producers done." % analyze.label("Threads"))

            for c in consumer_threads: c.join()               # Wait for each individual consumer threads
            aBuffer.CONSUMERS_DONE = True                     # Let timer thread know the consumer threads are done
            print("%s Consumers done." % analyze.label("Threads"))

            if aBuffer.KILL:
                f_out.write('%d\t%d\t%d\n' % (-1, -1, -1))    # Writes 3-part 'tuple' to OUTPUT_FILE to show KILL happened       
            f_out.close()                                     # Close the raw output file
        

        except KeyboardInterrupt:
            print("\n\nControl-C from terminal captured by buffer.py.  Setting 'aBuffer.KILL = True'")
            print("so the main loops in the producer and consumer functions see this and gracefully terminate.")
            print("If your code is stuck in a tight inner infinite loop, you'll probably have to press")
            print("Control-C again multiple times to kill everything more forcefully.\n\n")
            
            print("If the program doesn't gracefully stop, you can try to get an analysis of this run by entering:\n")
            print("    python3 buffer.py -A %s\n\n" % OUTPUT_FILE)

            kill_buffer(aBuffer, f_out)                       # Sets buffer.KILL and notes that in f_out 

            for p in producer_threads: p.join()               # Wait for each individual producer thread
            aBuffer.PRODUCERS_DONE = True                     # Let consumer threads know the producer threads are done
            print("Producer threads stopped.")

            for c in consumer_threads: c.join()               # Wait for each individual consumer thread
            aBuffer.CONSUMERS_DONE = True                     # Let timer thread know the consumer threads are done
            print("Consumer threads stopped.")
            f_out.close()                                     # Close the raw output file

            print("\nCalling analyze after user interrupt.")
            print("If you think you broke out of an infinite loop, there may be a lot of data to analyze.")
            print("If you don't want to wait on that analysis, enter Control-C again.\n\n")
            
        # adds the current run to the config, and prints the 'live' stats on it
        this_run = config.add_run(OUTPUT_FILE, aBuffer.KILL, args.matplot, print_details=True, print_section_start=False) 
    config.print_all_run_results()                            # Per config, print out the summary results of each run, and a combined view
analyze.print_summaries_and_grade(configs, args.grade)        # Print out an overall view of all configs, all runs and grade

print("\n\nUsed Target OOO = %5.2f%%.  %s" % (analyze.TARGET_OOO, "" if orig_target != args.outOfOrder else "(You can override this target via the -o parameter.)"))
print("Program Use Terminated.    (Run in directory '%s')\n" % pathlib.Path.cwd().name)
sys.exit()