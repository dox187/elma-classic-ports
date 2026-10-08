// The test ROM of the physics: runs the cases of test/physcases.txt
// (build/gen/phys_testcases.h) with phys_step and logs every step, for
// test/physrom.py to compare with the C description on the host
// (test/physdump.c) and to time the steps.
//
// It waits for phys_test_go (written by the Lua of physrom.py), then for
// each step writes 6 bytes to $7F0000 on (round, after 10922 steps): the
// events, and two Fletcher sums of the state (the direct page of phys.asm,
// phys_view and the other outputs); phys_test_steps counts them. At the end
// phys_test_done = 1. A warp item of a case moves the bike: its front wheel
// (kor2) onto an object, or 2000 m to the right (out of the level).
#include <snes.h>
#include "phys.h"
#include "phys_testcases.h"

extern u8 phys_dpa[];

volatile u16 phys_test_go, phys_test_full, phys_test_done, phys_test_steps;

#define PHYS_STATE 142
#define LOG_STEPS 10922                  // steps of 6 bytes in the bank

static u16 Sa, Sb;

static void sum( const u8* p, u16 n ) {
	while( n ) {
		Sa += *p++;
		Sb += Sa;
		n--;
	}
}

// The view without its padding, and the other outputs:
static void sum_outputs( void ) {
	sum( (const u8*)&phys_view, 10 );
	sum( (const u8*)&phys_view + 12, 38 );
	sum( (const u8*)&phys_bump, 2 );
	sum( (const u8*)&phys_eaten, 2 );
	sum( (const u8*)&phys_friction, 2 );
	sum( (const u8*)&phys_wheel_omega, 2 );
	sum( (const u8*)&phys_apples_left, 2 );
	sum( &phys_volt_age, 1 );
	sum( &phys_volt1, 1 );
}

// The offsets of the positions in the state: kor1, kor2, kor4, the rider
// and the head (x, then y 4 bytes on):
static const u8 warp_off[5] = { 0, 24, 48, 72, 88 };

static void warp( u16 obj ) {
	s32 dx, dy;
	s32* p;
	u16 k;
	if( obj == 0xFFFF ) {
		dx = 0x07D00000L;
		dy = 0;
	}
	else {
		p = (s32*)(phys_dpa+24);
		dx = phys_objs[obj].x;
		dx -= p[0];
		dy = phys_objs[obj].y;
		dy -= p[1];
	}
	k = 0;
	while( k < 5 ) {
		p = (s32*)(phys_dpa+warp_off[k]);
		p[0] += dx;
		p[1] += dy;
		k++;
	}
}

int main( void ) {
	u16 c, i, j, ev, input, logn;
	u8* log;
	consoleInit();
	*(u8*)0x4200 = 0;                   // no NMI: the steps are timed
	phys_test_done = 0;
	phys_test_steps = 0;
	while( !phys_test_go ) {
	}
	log = (u8*)0x7F0000L;
	logn = 0;
	c = 0;
	while( c < PT_NCASES ) {
		phys_level( pt_case_level[c] );
		ev = 0;
		i = pt_case_first[c];
		while( i < pt_case_first[c]+pt_case_items[c] && !(ev & (PH_DEAD | PH_FINISH)) ) {
			input = pt_item_input[i];
			if( input & 96 ) {
				warp( (input & 32) ? 0xFFFF : pt_item_count[i] );
				i++;
				continue;
			}
			j = 0;
			while( j < pt_item_count[i] ) {
				ev = phys_step( input & 15 );
				if( (input & 128) && j == 0 )
					phys_turn();
				Sa = Sb = 0;
				sum( phys_dpa, PHYS_STATE );
				sum_outputs();
				log[0] = (u8)ev;
				log[1] = (u8)(ev >> 8);
				log[2] = (u8)Sa;
				log[3] = (u8)(Sa >> 8);
				log[4] = (u8)Sb;
				log[5] = (u8)(Sb >> 8);
				log += 6;
				logn++;
				if( logn == LOG_STEPS ) {
					logn = 0;
					log = (u8*)0x7F0000L;
				}
				phys_test_steps++;
				if( ev & (PH_DEAD | PH_FINISH) )
					break;
				j++;
			}
			i++;
		}
		c++;
	}
	phys_test_done = 1;
	while( 1 ) {
	}
	return 0;
}
