#include "far.h"
#include <mapper.h>

const uint8_t* far_ptr( uint32_t lin ) {
	// The bank actually there: the physics and the menus map their own.
	uint8_t bank = (uint8_t)(lin >> 13);
	if( bank != get_prg_8000() )
		set_prg_8000( bank );
	return (const uint8_t*)(0x8000u | ((uint16_t)lin & 0x1fff));
}
