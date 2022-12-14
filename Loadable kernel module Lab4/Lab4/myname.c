/**
 * Kernel module that communicates with /proc file system.
 */

#include <linux/init.h>
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/proc_fs.h>
#include <linux/vmalloc.h>
#include <asm/uaccess.h>


#define BUFFER_SIZE 128
#define LAB_NAME    "LAB4"
#define PROC_NAME   "myname"



/**
 * Function prototypes
 */
ssize_t proc_read(struct file *file, char *buf, size_t count, loff_t *pos);



/* Try to handle multiple kernels for students on older Ubuntu images, or M1 Macs.
 * If more or less up to date, use the  proc_ops         parameter to proc_create.
 * Otherwise, try to use the older      file_operations  parameter to proc_create. */

#include <linux/version.h>

#if LINUX_VERSION_CODE >= KERNEL_VERSION(5,8,0)
const static struct proc_ops my_ops = {
        .proc_read = proc_read,
};
#else
static struct file_operations my_ops = {
        .owner = THIS_MODULE,
        .read = proc_read,
};
#endif



/* This function is called when the module is loaded. */
int proc_init(void)
{
        
	proc_create(PROC_NAME, 0, NULL, &my_ops);						

       
	printk(KERN_INFO "LAB4: Loading module by Quantez Merchant\n"); 	 

	return 0;

}


/* This function is called when the module is removed. */
void proc_exit(void) {

        
	remove_proc_entry(PROC_NAME, NULL);				


	printk(KERN_INFO "LAB4: Removing module by Quantez Merchant\n"); 
}


/**
 * This function is called each time the /proc/myname is read.
 * 
 * When a user triggers this call, the function is called repeatedly by the system until you return 0, so
 * be careful to return 0 when you know you're done.  Note that you have to return at least
 * once with a non-zero value to get your data back out to the user.  
 * 
 * If you get a loop at the command line when you 'cat /proc/myname', just hit Ctrl-C to break it.
 * 
 * See the lab write-up for details on what your proc_read is supposed to output.
 */

ssize_t proc_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
        
	int rv = 0;
	int crv = 0;
        char buffer[BUFFER_SIZE];
        static int completed = 0;
	static int counter = 1;
	char fName [] = "Quantez";
	char lName [] = "Merchant";

        if (completed) {
                completed = 0;
                return 0;
        }

        completed = 1;

	if(counter%2 == 0){

        	rv = sprintf(buffer, "LAB4: myname[%d] = %s\n", counter,lName);
	
	}else{
	
		rv = sprintf(buffer, "LAB4: myname[%d] = %s\n", counter,fName);
	
	}

	counter++;

	crv = raw_copy_to_user(buf,buffer,rv);				
	
	if(crv > 0){							
		printk("Error copying contents of buffer to userspace.\n");
	}

        return rv;
}


/* Macros for registering module entry and exit points. */
module_init( proc_init );
module_exit( proc_exit );

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Module");
MODULE_AUTHOR("SGG-MORE");

