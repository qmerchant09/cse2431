
import threading

# =======================================================================================================
# This is the producer thread function.  
# It reads items from f_in (which points to the already opened file INPUT_FILE), and 
# places the read item into the bounded buffer at location IN (e.g., buffer[IN]).
#
# producer_num:  the id of the thread running the function
# f_in:          open file handle to INPUT_FILE
# buffer:        buffer class object, already created
# locks:         set of locks, already created

def student_producer(producer_num, f_in, buffer, locks):
    # The buffer.py code catches a terminal kill signal, and sets buffer.KILL so producers/consumers see it and stop.
    # Students do NOT need to write any code to handle these interrupts.
    while not buffer.KILL:     
        
        # ------ PLACE YOUR PRODUCER CODE BELOW THIS LINE ------

        locks.producer_file_in.acquire()                                 # Lock the file input 
        line = f_in.readline()                                           # Read a line of data from f_in into the variable 'line' 

        try:              item  = int(line)                              # LINE P-1:  DO NOT CHANGE OR REORDER THIS LINE RELATIVE TO P-# LABELED LINES!  Turns the read input line into an integer 'item'
        except Exception: item  = 0                                      # LINE P-2:  DO NOT CHANGE OR REORDER THIS LINE RELATIVE TO P-# LABELED LINES!  If input item bad, sets to invalid.  With good code, this shouldn't happen.  (e.g., shouldn't try to use data beyond end of file)      
        locks.producer_file_in.release()                                 # Release the file input lock


        if not item == 0:                                                # Break the loop if the item produced is invalid 
        
            locks.producer_buffer.acquire()                              # Lock the buffer
            while(((buffer.IN + 1) % buffer.NUM_SLOTS) == buffer.OUT):   # While the buffer is full do nothing 
                pass 
            buffer.ITEMS[buffer.IN] = (item, producer_num)               # LINE P-3:  DO NOT CHANGE OR REORDER THIS LINE RELATIVE TO P-# LABELED LINES!  Inserts a 2-part tuple into buffer.
            buffer.IN = (buffer.IN + 1) % buffer.NUM_SLOTS               # Increment the position of IN in the buffer 
            locks.producer_buffer.release()                              # Release the lock on the buffer
            
        else:
            return    

        # ------ PLACE YOUR PRODUCER CODE ABOVE THIS LINE ------

# ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ 





# =======================================================================================================
# This is the consumer thread function.  
# It reads items from the bounded buffer at location OUT (e.g., buffer[OUT]) and 
# writes the output item to f_out (which points to the already opened file OUTPUT_FILE)
#
# consumer_num:  the id of the thread running the function
# f_out:         open file handle to OUTPUT_FILE
# buffer:        buffer class object, already created
# locks:         set of locks, already created

def student_consumer(consumer_num, f_out, buffer, locks):
    # The buffer.py code catches a terminal kill signal, and sets buffer.KILL so producers/consumers see it and stop.
    # Students do NOT need to write any code to handle these interrupts.
    while not buffer.KILL:
        
        # ------ PLACE YOUR CONSUMER CODE BELOW THIS LINE ------
       
        locks.consumer_buffer.acquire()                                             # Lock the buffer
        while buffer.IN == buffer.OUT and not buffer.PRODUCERS_DONE:                # While the buffer is empty, and the producers are still producing, do nothing
            pass

        try:              (item, producer_num) = buffer.ITEMS[buffer.OUT]           # LINE C-1:  DO NOT CHANGE OR MOVE THIS LINE RELATIVE TO C-# LABELED LINES!  Pulls a 2-part tuple out of buffer.
        except Exception: (item, producer_num) = (0, 0)                             # LINE C-2:  DO NOT CHANGE OR MOVE THIS LINE RELATIVE TO C-# LABELED LINES!  Sets the tuple to 'invalid' info if bad data pulled from buffer.
        buffer.OUT = (buffer.OUT + 1) % buffer.NUM_SLOTS                            # Increment the position of OUT in the buffer
        locks.consumer_buffer.release()                                             # Release the lock on the buffer
        
       
        locks.consumer_file_out.acquire()                                           # Lock f_out
        f_out.write('%d\t%d\t%d\n' % (item, producer_num, consumer_num))            # LINE C-3:  DO NOT CHANGE OR MOVE THIS LINE RELATIVE TO C-# LABELED LINES!  Writes a 3-part 'tuple' (really, tab-separated data) to f_out.
        locks.consumer_file_out.release()                                           # Release the lock on f_out

        if buffer.PRODUCERS_DONE and buffer.IN == buffer.OUT:                       # If the producers are done producing and the buffer is empty stop consuming 
            return                                                          
        
        # ------ PLACE YOUR CONSUMER CODE ABOVE THIS LINE ------


# ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ 

