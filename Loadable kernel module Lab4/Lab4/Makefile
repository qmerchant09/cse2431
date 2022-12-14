obj-m += myname.o
PROC_NAME=myname
LAB_NAME=LAB4

all:
	make -C /lib/modules/$(shell uname -r)/build M=$(shell pwd) modules
clean:
	make -C /lib/modules/$(shell uname -r)/build M=$(shell pwd) clean


grade:
	sudo rmmod $(PROC_NAME)  ||:

	@echo ""
	@echo ""
	make clean

	@echo ""
	@echo ""
	make all

	@echo ""
	@echo ""
	sudo insmod $(PROC_NAME).ko

	@echo ""
	@echo ""
	@echo "LSMOD: Should find $(PROC_NAME) in the list."
	lsmod | grep $(PROC_NAME)

	@echo ""
	@echo ""
	@echo "Reading /proc/$(PROC_NAME) 5 times"
	@cat /proc/$(PROC_NAME)
	@cat /proc/$(PROC_NAME)
	@cat /proc/$(PROC_NAME)
	@cat /proc/$(PROC_NAME)
	@cat /proc/$(PROC_NAME)

	@echo ""
	@echo ""
	sudo rmmod $(PROC_NAME)

	@echo ""
	@echo ""
	@echo "LSMOD: Should not find $(PROC_NAME) in the list now."
	lsmod | grep $(PROC_NAME) ||:

	@echo ""
	@echo ""
	@echo "Try to read /proc/$(PROC_NAME).  Should fail now."
	@cat /proc/$(PROC_NAME) ||:

	@echo ""
	@echo ""
	@echo "DMESG: Should see student as last pair of 'Loading' and 'Removing' messages."
	dmesg -T | grep -i $(LAB_NAME) | tail -n 4
	@echo ""

