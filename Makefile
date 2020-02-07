SOURCES = $(wildcard *.py)
DESTDIR=/home/pi/app/zorkb

install: $(SOURCES)
	cp $(SOURCES) $(DESTDIR)
