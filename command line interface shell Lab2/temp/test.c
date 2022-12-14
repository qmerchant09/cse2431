#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/wait.h>

#define MAX_LINE     80

/* setup() reads in the next command line string stored in inputBuffer, separating it
into distinct tokens using whitespace as delimiters. setup() modifies the args
parameter so that it holds pointers to the null-terminated strings that are the tokens in
the most recent user command line as well as a NULL pointer, indicating the end of
the argument list, which comes after the string pointers that have been assigned to args. */

void setup(char inputBuffer[], char *args[], int *background)
{

    int length,                                          /* number of characters in the command line */
        start,                                           /* index for the beginning of next command parameter */
        i,                                               /* index to access inputBuffer arrray */
        j;                                               /* index of where to place the next parameter into args[] */

    
    length = read(STDIN_FILENO, inputBuffer, MAX_LINE);  /* number of characters user entered */

    start = -1;
    j     = 0;

    if (length == 0) {
        /* Ctrl-D was entered, end of user command stream 
           Want to make it clear we ended here.  Without output, that's not clear. 
           This is helpful when the command entered is the myshell program itself. */
        printf("\n\nProgram use terminated.\n\n");
        exit(0);                                         /* 0 is success as a return status */
    }

    if (length < 0) {
        perror("error reading the command");
        exit(1);                                         /* Terminate with error code of 1 */
    }

    
    for (i = 0; i < length; i++) {                       /* Check every character in the inputBuffer array */
        switch (inputBuffer[i]) {
            case ' '  :
            case '\t' :                                  /* Argument separators */
                if(start != -1) {
                    args[j] = &inputBuffer[start];       /* Set up pointer */
                    j++;                                 /* increment number of args */
                }
                inputBuffer[i] = '\0';                   /* Add a null character '\0'; making a C 'string' */
                start = -1;                              /* Note that no longer reading in a word. */
                break;


            case '\n':                                   /* Final char examined */
                if (start != -1) {
                    args[j] = &inputBuffer[start];       /* Set up pointer */
                    j++;                                 /* increment number of args */
                }
                inputBuffer[i] = '\0';                   /* Add a null character '\0'; making a C 'string' */
                args[j] = NULL;                          /* No more arguments to this command */
                break;


            case '&':                                    /* background character */
                *background = 1;                         /* set background */
                inputBuffer[i] = '\0';                   /* Add a null character '\0'; making a C 'string' */
                break;


            default :                                    /* Some other character */
                if (start == -1)                         /* if not alreadying reading in next word... */
                    start = i;                           /* ... mark its start */
        }
    }
    args[j] = NULL;                                      /* Just in case the input line was > 80 */
    
    for (i = 0; i < j; i++)
        printf("args %d: %s\n",i,args[i]);               /* print each arg */  
    printf("backgr: %d\n\n", *background);               /* ... and background status */
}


int main(void)
{
    char  inputBuffer[MAX_LINE];                         /* buffer to hold the command entered */
    int   background,echeck;					 /* equals 1 if a command is followed by '&' */
    int	  counter = 1;					 /* counter used for command prompt */
    char *args[MAX_LINE/2+1];                            /* command line arguments */

    pid_t pid;

    while (1) {
        background   = 0;
	
        printf("\nCOMMAND [%d] > ",counter);              /* display a prompt */
        fflush(stdout) ;                                 /* since prompt has no '\n' need to flush the output so prompt is visible */
        setup(inputBuffer,args,&background);             /* get next command */
		
	pid = fork();

	if(pid < 0) {
			
		printf("Error creating child.\n");

	}else if(pid == 0) {

		if(strcmp(args[0],"cd") == 0){
			
			if(args[1] == NULL){
				
				printf("Error: no directory specified.\n");
			
			}else if (chdir(args[1]) != 0){
				
				printf("Error: %s directory doesnt exist.\n",args[1]);
			}	
		}else{
		
			echeck = execvp(args[0],args);
			printf("Error: %s is not a valid command.\n", args[0]);
			exit(echeck);
		}

	}else {
		if(background == 0){
			waitpid(pid, &echeck, 0);               
                }
	}
	counter++;    
    }
    return 0;
}
/* ADD COMMENTS, MAKE BETTER ERROR MESSAGES, DO GENERAL CLEANUP */
