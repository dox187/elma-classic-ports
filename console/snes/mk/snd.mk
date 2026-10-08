# The sounds: the driver of the SPC700 (spc/driver.asm) and the samples of
# elma.res for it (tools/gen_snd.py).
SPC_AS = $(DEVKIT)/bin/wla-spc700
GEN_ASM += $(GEN)/snd.asm
GEN_H += $(GEN)/snd.inc

$(BUILD)/spc/driver.bin: spc/driver.asm | check-tools
	@mkdir -p $(BUILD)/spc
	$(SPC_AS) -o $(BUILD)/spc/driver.o spc/driver.asm
	@echo '[objects]' > $(BUILD)/spc/driver.link
	@echo $(BUILD)/spc/driver.o >> $(BUILD)/spc/driver.link
	$(LD) -b -S $(BUILD)/spc/driver.link $@

$(GEN)/snd.asm $(GEN)/snd.inc &: tools/gen_snd.py tools/elmadata.py \
		$(BUILD)/spc/driver.bin $(GEN)/data_names
	$(PYTHON) tools/gen_snd.py $(ELMA_RES) $(BUILD)/spc/driver.bin $(GEN)
