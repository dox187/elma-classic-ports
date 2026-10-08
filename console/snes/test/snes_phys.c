// The test ROM of the physics: runs the cases of test/physcases.txt
// (build/gen/phys_testcases.h) with phys_step and logs every step, for
// test/physrom.py to compare with the C description on the host
// (test/physdump.c) and to time the steps.
//
// It waits for phys_test_go (written by the Lua of physrom.py), then for
// each step writes 6 bytes to $7F0000 on: the events, and two Fletcher sums
// of the state (the direct page of phys.asm, phys_view and the other
// outputs). The steps of the case phys_test_full (if any) are also written
// whole to $7E8000 (PHYS_DUMP bytes each, at most 160 of them). At the end
// phys_test_done = 1.
#include <snes.h>
#include "phys.h"
#include "phys_testcases.h"

extern u8 phys_dpa[];

volatile u16 phys_test_go, phys_test_full, phys_test_done, phys_test_steps;

#define PHYS_STATE 142
#define PHYS_DUMP 208

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

static void copy( u8* dst, const u8* src, u16 n ) {
	while( n ) {
		*dst++ = *src++;
		n--;
	}
}

int main( void ) {
	u16 c, i, j, ev, input, full, nfull;
	u8* log;
	u8* dump;
	consoleInit();
	*(u8*)0x4200 = 0;                   // no NMI: the steps are timed
	phys_test_done = 0;
	phys_test_steps = 0;
	while( !phys_test_go ) {
	}
	log = (u8*)0x7F0000L;
	c = 0;
	while( c < PT_NCASES ) {
		phys_level( pt_case_level[c] );
		full = (c == phys_test_full);
		dump = (u8*)0x7E8000L;
		nfull = 0;
		ev = 0;
		i = pt_case_first[c];
		while( i < pt_case_first[c]+pt_case_items[c] && !(ev & (PH_DEAD | PH_FINISH)) ) {
			input = pt_item_input[i];
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
				phys_test_steps++;
				if( full && nfull < 160 ) {
					nfull++;
					copy( dump, phys_dpa, PHYS_STATE );
					copy( dump+PHYS_STATE, (u8*)&phys_view, 52 );
					copy( dump+PHYS_STATE+52, (u8*)&phys_bump, 2 );
					copy( dump+PHYS_STATE+54, (u8*)&phys_eaten, 2 );
					copy( dump+PHYS_STATE+56, (u8*)&phys_friction, 2 );
					copy( dump+PHYS_STATE+58, (u8*)&phys_wheel_omega, 2 );
					copy( dump+PHYS_STATE+60, (u8*)&phys_apples_left, 2 );
					dump[PHYS_STATE+62] = phys_volt_age;
					dump[PHYS_STATE+63] = phys_volt1;
					dump[PHYS_STATE+64] = (u8)ev;
					dump[PHYS_STATE+65] = (u8)(ev >> 8);
					dump += PHYS_DUMP;
				}
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
