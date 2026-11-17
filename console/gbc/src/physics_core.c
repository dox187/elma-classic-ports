#ifdef __SDCC
#pragma bank 8
#endif
// Fixed-point dynamics adapted from the NES C reference, with GBC clock
// constants and exact host implementations of the SM83 arithmetic helpers.
#include "physics_core.h"
#include "physics_math.h"
#include "physics_math32.h"
#include "riding_constants.h"

// rider_limit clamps x/y before its ellipse projection. Keep the narrow
// square-root contract valid if the rider limits change in a later port.
#define RIDING_ELLIPSE_X_MAX ((1L*RIDER_RIGHT*C_ELLIPSE_M+(1L<<(C_ELLIPSE_E-1)))>>C_ELLIPSE_E)
#if RIDING_ELLIPSE_X_MAX*RIDING_ELLIPSE_X_MAX+1L*RIDER_TOP*RIDER_TOP >= 1048576L
#error Rider ellipse exceeds the exact 20-bit square-root input bound
#endif

/* Guaranteed-inside rider regions, as used in the SNES port. These bounds
 * use this kernel's exact rounded coefficients; every other pose falls back. */
static const int16_t Ellipse_inside_y[]={RIDING_ELLIPSE_INSIDE_Y_VALUES};

bike_t Bike;
#ifdef __SDCC
#include <stddef.h>
typedef char suspension_layout[
    sizeof(circle_t)==22 && offsetof(circle_t,vx)==8 && offsetof(circle_t,vy)==12 &&
    offsetof(circle_t,alfa)==16 && offsetof(circle_t,omega)==20 &&
    offsetof(bike_t,dbrake)==95 &&
    offsetof(bike_t,body)==0 && offsetof(bike_t,wheel)==22 &&
    sizeof(riding_torque32_t)==24 && offsetof(riding_torque32_t,relx)==0 &&
    offsetof(riding_torque32_t,rely)==8 && offsetof(riding_torque32_t,kx)==16 &&
    offsetof(riding_torque32_t,ky)==20 ? 1 : -1];
void riding_anchor32(circle_t*,int16_t,int16_t,int16_t*) __sdcccall(0);
int32_t riding_suspension32(const int16_t*,const int16_t*,int32_t,int32_t*,int32_t*,riding_torque32_t*) __sdcccall(0);
void riding_brake32(int16_t*) __sdcccall(0);
uint8_t riding_recip_index(int16_t,int16_t) __sdcccall(0);
void riding_rider_vectors32(int16_t,int16_t,int16_t*) __sdcccall(0);
void riding_rider_move32(int32_t,int32_t) __sdcccall(0);
#endif

static int16_t Cs, Sn;   // cos and sin of the body's angle
static int32_t Oms;      // body angular velocity, see C_OMS

static void angle( void ) {
	uint16_t a = (uint16_t)(Bike.body.alfa >> RIDING_ANGLE_SHIFT);
	Cs = fcos( a );
	Sn = fsin( a );
}

/* Rider, renderer and head collision all observe the same completed step. */
static void head_position(void) {
 int32_t x=Bike.rider_x,y=Bike.rider_y;
 int16_t hc,hs;
 angle();hc=KMUL(Cs,C_H_X);hs=KMUL(Sn,C_H_X);
 if(!Bike.turned){hc=-hc;hs=-hs;}
 Bike.head_x=x+(int32_t)(hc-KMUL(Sn,C_H_Y))*256L;
 Bike.head_y=y+(int32_t)(hs+KMUL(Cs,C_H_Y))*256L;
}

#ifdef __SDCC
#define move riding_move32
#else
static void move(circle_t *k) {
 k->alfa += (uint32_t)((int32_t)k->omega * 128L);
 k->rx += (int32_t)k->vx * 4L;
 k->ry += (int32_t)k->vy * 4L;
}
#endif

// vezeto_hatarolas: keeps the rider over the seat.
static void rider_limit( void ) {
	int16_t dx = sat16( riding_sra8(Bike.rider_x-Bike.body.rx) );
	int16_t dy = sat16( riding_sra8(Bike.rider_y-Bike.body.ry) );
	int16_t x = dotq14( dx, dy, Cs, Sn );
	int16_t y = dotq14( dy, dx, Cs, -Sn );
	uint8_t moved = 0;
	if( Bike.turned )
		x = -x;
	int16_t under;
#if RIDING_SEAT_FAST_ENABLED
    under=0;
    if(x>RIDING_SEAT_FAST_X || y<RIDING_SEAT_FAST_Y || y>RIDER_TOP)
#endif
        under=KMUL(y-SEAT_Y,C_SEAT_NY)-KMUL(x-SEAT_X,C_SEAT_NX);
	if( under < 0 ) {
		x += KMUL( under, C_SEAT_NX );
		y -= KMUL( under, C_SEAT_NY );
		moved = 1;
	}
	if( y > RIDER_TOP ) {
		y = RIDER_TOP;
		moved = 1;
	}
	if( x < RIDER_LEFT ) {
		x = RIDER_LEFT;
		moved = 1;
	}
	if( x > RIDER_RIGHT ) {
		x = RIDER_RIGHT;
		moved = 1;
	}
	if( x > 0 && y > 0 && y > Ellipse_inside_y[(uint16_t)x>>RIDING_ELLIPSE_BUCKET_SHIFT] ) {
		int16_t xs = KMUL( x, C_ELLIPSE );
		int32_t d2 = mul16( xs, xs )+mul16( y, y );
		if( d2 > (int32_t)RIDER_TOP*RIDER_TOP ) {
			int16_t d = (int16_t)riding_isqrt20( (uint32_t)d2 );
			x = (int16_t)riding_div_u32_u16((uint32_t)mul16(x,RIDER_TOP),(uint16_t)d);
			y = (int16_t)riding_div_u32_u16((uint32_t)mul16(y,RIDER_TOP),(uint16_t)d);
			moved = 1;
		}
	}
	if( !moved )
		return;
	if( Bike.turned )
		x = -x;
	Bike.rider_x = Bike.body.rx + ((int32_t)dotq14( x, y, Cs, -Sn ) << 8);
	Bike.rider_y = Bike.body.ry + ((int32_t)dotq14( x, y, Sn, Cs ) << 8);
}

// beallitvezeto, at the same rate as the body and wheels:
static void rider( int32_t gx, int32_t gy ) {
	rider_limit();
#ifdef __SDCC
	int16_t v[4];
	riding_rider_vectors32(-KMUL(Sn,C_RREST),KMUL(Cs,C_RREST),v);
	int16_t dirx=v[0],diry=v[1],dx=v[2],dy=v[3];
#else
	int16_t dirx = sat16( ((Bike.body.rx-Bike.rider_x) >> 4)-KMUL( Sn, C_RREST ) );
	int16_t diry = sat16( ((Bike.body.ry-Bike.rider_y) >> 4)+KMUL( Cs, C_RREST ) );
	int16_t dx = sat16( (Bike.rider_x-Bike.body.rx) >> 4 );
	int16_t dy = sat16( (Bike.rider_y-Bike.body.ry) >> 4 );
#endif
	// The velocity of the body there:
	int32_t relx = Bike.rider_vx-(Bike.body.vx+riding_mulq32(Oms,-dy,14));
	int32_t rely = Bike.rider_vy-(Bike.body.vy+riding_mulq32(Oms,dx,14));
	int32_t ax = KMUL32(dirx,C_RIDER_S)-KMUL32(relx,C_RIDER_F)+gx;
	int32_t ay = KMUL32(diry,C_RIDER_S)-KMUL32(rely,C_RIDER_F)+gy;
#ifdef __SDCC
	riding_rider_move32(ax,ay);
#else
	Bike.rider_vx += ax;
	Bike.rider_vy += ay;
	Bike.rider_x += Bike.rider_vx * 4L;
	Bike.rider_y += Bike.rider_vy * 4L;
#endif
}

void ph_init( int32_t x, int32_t y ) {
	uint8_t* p = (uint8_t*)&Bike;
	for( uint16_t i = 0; i < sizeof( bike_t ); i++ )
		p[i] = 0;
	Bike.gravity = GRAV_DOWN;
	Bike.body.rx = x+F_BODY_X;
	Bike.body.ry = y+F_BODY_Y;
	Bike.wheel[0].rx = x;
	Bike.wheel[0].ry = y;
	Bike.wheel[1].rx = x+F_WHEELBASE;
	Bike.wheel[1].ry = y;
	Bike.rider_x = x+F_BODY_X;
	Bike.rider_y = y+F_RIDER_Y;
	Bike.head_x = Bike.rider_x;
	Bike.head_y = Bike.rider_y+F_HEAD_Y;
	head_position();
}

void ph_turn( void ) {
	Bike.turned = !Bike.turned;
	head_position();
}

// 2^30/d^2 for d^2 in steps of 2^13 u^2 (distances below 0.36 m count as
// 0.36 m):
static const int16_t Recip_d2[] = {
#include "../../nes/src/recip.inc"
};

#if !defined(__SDCC) || !defined(RIDING_COEFFICIENT_LOOKUP)
static int16_t clamp_w( int32_t w ) {
	if( w > 16383 ) return 16383;
	if( w < -16383 ) return -16383;
	return (int16_t)w;
}
#endif

/* ph_step follows the single global Bike and is never called by interrupts.
 * Give its arrays fixed SM83 addresses; HOST keeps automatic storage. */
#ifdef __SDCC
#define STEP_LOCAL static
#else
#define STEP_LOCAL
#endif

uint8_t ph_step( uint8_t input ) {
	int32_t previous_head_x=Bike.head_x,previous_head_y=Bike.head_y;
#ifndef __SDCC
    angle();
#else
    /* Reset/turn and the preceding step end with head_position(), which
     * refreshes Cs/Sn after the only runtime writes to body.alfa. */
#endif
	Oms = KMUL32((int32_t)Bike.body.omega,C_OMS);

	// Gas and brake:
	uint8_t brake = input & IN_BRAKE;
	if( brake && !Bike.brake_was ) {
		Bike.dbrake[0] = Bike.wheel[0].alfa-Bike.body.alfa;
		Bike.dbrake[1] = Bike.wheel[1].alfa-Bike.body.alfa;
	}
	Bike.brake_was = brake;
	STEP_LOCAL int16_t tq[2];
	tq[0] = 0; tq[1] = 0;
	if( input & IN_GAS ) {
		if( Bike.turned ) {
			if( Bike.wheel[0].omega > -WHEEL_MAXW )
				tq[0] = -GAS_TQ;
		}
		else if( Bike.wheel[1].omega < WHEEL_MAXW )
			tq[1] = GAS_TQ;
	}
	if( brake ) {
#if defined(__SDCC) && defined(RIDING_COEFFICIENT_LOOKUP)
        riding_brake32(tq);
#else
		for( uint8_t k = 0; k < 2; k++ ) {
			// Brake deflection accumulates: wrapping at half a turn reverses
			// the spring torque during hard landings (Hi Flyer's final pipe).
			int32_t da = riding_sra8((int32_t)(Bike.wheel[k].alfa-(Bike.body.alfa+Bike.dbrake[k])));
			/* da is signed24 after >>8; its uint8-factor product and round
             * fit signed32, so this is exact and avoids generic long multiply. */
            int32_t spring = KMUL32(da,C_BRAKE_A);
			int16_t dw = clamp_w((int32_t)Bike.wheel[k].omega-Bike.body.omega);
			tq[k] = sat16( -spring-KMUL( dw, C_BRAKE_W ) );
		}
#endif
	}

	// Forces between the wheels and the body (erokszamitasa). The anchors
	// of the springs, from the rotation of (K_X, -K_Y):
	int16_t a = KMUL( Cs, C_K_X ), b = KMUL( Sn, C_K_Y );
	int16_t c = KMUL( Sn, C_K_X ), d = KMUL( Cs, C_K_Y );
	STEP_LOCAL int16_t gsx[2], gsy[2];
	gsx[1] = a+b;
	gsy[1] = c-d;
	gsx[0] = b-a;
	gsy[0] = -c-d;

	STEP_LOCAL int32_t dvx[2], dvy[2];
	int32_t ts = 0;
	STEP_LOCAL riding_torque32_t damping;
#if defined(__SDCC) && defined(RIDING_COEFFICIENT_LOOKUP)
    ts = riding_suspension32(gsx,gsy,Oms,dvx,dvy,&damping);
    for( uint8_t k = 0; k < 2; k++ ) {
        int16_t kx=damping.kx[k],ky=damping.ky[k];
#else
	for( uint8_t k = 0; k < 2; k++ ) {
		circle_t* w = &Bike.wheel[k];
		#ifdef __SDCC
        STEP_LOCAL int16_t anchor[4];
        riding_anchor32(w,gsx[k],gsy[k],anchor);
        int16_t gx=anchor[0],gy=anchor[1];
#else
        int16_t gx = sat16( ((Bike.body.rx-w->rx) >> 4)+((int32_t)gsx[k] << 4) );
        int16_t gy = sat16( ((Bike.body.ry-w->ry) >> 4)+((int32_t)gsy[k] << 4) );
#endif
		dvx[k] = KMUL32(gx,C_SPRING_W);
		dvy[k] = KMUL32(gy,C_SPRING_W);
		ts += mul16( gsx[k], gy )-mul16( gsy[k], gx );

		#ifdef __SDCC
        int16_t kx=anchor[2],ky=anchor[3];
#else
        int16_t kx = sat16( riding_sra8(w->rx-Bike.body.rx) );
        int16_t ky = sat16( riding_sra8(w->ry-Bike.body.ry) );
#endif
		// The velocity of the body at the wheel against the wheel's:
		int32_t relx = Bike.body.vx-w->vx-riding_mulq32(Oms,ky,10);
		int32_t rely = Bike.body.vy-w->vy+riding_mulq32(Oms,kx,10);
		dvx[k] += KMUL32(relx,C_FRIC_W);
		dvy[k] += KMUL32(rely,C_FRIC_W);
		damping.kx[k]=kx;damping.ky[k]=ky;
		damping.relx[k]=relx;damping.rely[k]=rely;
#endif

		if( tq[k] ) {
			// 1/d^2 from a table, with d^2 from the high bits of k:
			#ifdef __SDCC
            uint8_t d2=riding_recip_index(kx,ky);
#else
            int16_t kx8 = kx >> 4, ky8 = ky >> 4;
			if( kx8 > 127 ) kx8 = 127;
			if( kx8 < -127 ) kx8 = -127;
			if( ky8 > 127 ) ky8 = 127;
			if( ky8 < -127 ) ky8 = -127;
			uint16_t d2 = (uint16_t)((kx8*kx8 + ky8*ky8) >> 5);
			#endif
            int16_t rec = Recip_d2[d2 > 255 ? 255 : d2];
			int32_t tr = KMUL32(riding_mulshift32((int32_t)tq[k],rec,8),C_REACT);
			dvx[k] += riding_mulq32(tr,ky,14);
			dvy[k] -= riding_mulq32(tr,kx,14);
		}
	}
	// The body gets all the forces between them, of the opposite sign, with
	// 20 times the mass of a wheel:
	int32_t dvbx = -KMUL32(dvx[0]+dvx[1],C_TWENTIETH);
	int32_t dvby = -KMUL32(dvy[0]+dvy[1],C_TWENTIETH);
	int32_t dwb = -(int32_t)KMUL(sat16(riding_sra8(ts)>>2),C_SPRING_T)
	              -KMUL(riding_torque_input32(&damping),C_FRIC_T);

	// Volts:
	int16_t oldomega = Bike.body.omega;
	uint8_t volt = input & (IN_VOLT_RIGHT | IN_VOLT_LEFT);
	if( Bike.volt[0] && (volt || --Bike.volt[0] == 0) ) {
		Bike.body.omega += LOKET;
		if( Bike.body.omega > Bike.volt_omega[0] )
			Bike.body.omega = Bike.volt_omega[0];
		if( Bike.body.omega > 0 ) {
			Bike.body.omega -= OMEGAVALT;
			if( Bike.body.omega < 0 )
				Bike.body.omega = 0;
		}
		Bike.volt[0] = 0;
	}
	if( Bike.volt[1] && (volt || --Bike.volt[1] == 0) ) {
		Bike.body.omega -= LOKET;
		if( Bike.body.omega < Bike.volt_omega[1] )
			Bike.body.omega = Bike.volt_omega[1];
		if( Bike.body.omega < 0 ) {
			Bike.body.omega += OMEGAVALT;
			if( Bike.body.omega > 0 )
				Bike.body.omega = 0;
		}
		Bike.volt[1] = 0;
	}
	if( input & IN_VOLT_RIGHT ) {
		Bike.volt[0] = VOLT_STEPS;
		Bike.volt_omega[0] = Bike.body.omega;
		Bike.body.omega -= LOKET;
	}
	if( input & IN_VOLT_LEFT ) {
		Bike.volt[1] = VOLT_STEPS;
		Bike.volt_omega[1] = Bike.body.omega;
		Bike.body.omega += LOKET;
	}
	if( volt ) {
		int32_t dw = KMUL32((int32_t)Bike.body.omega-oldomega,C_OMS);
		int16_t dx = sat16( (Bike.rider_x-Bike.body.rx) >> 4 );
		int16_t dy = sat16( (Bike.rider_y-Bike.body.ry) >> 4 );
		Bike.rider_vx += riding_mulq32(dw,-dy,14);
		Bike.rider_vy += riding_mulq32(dw,dx,14);
	}

	// Gravity, with its fraction carried over:
	int16_t g = G_INT;
	uint8_t f = Bike.gfrac;
	Bike.gfrac = f+G_FRAC;
	if( Bike.gfrac < f )
		g++;
	int16_t gx = 0, gy = 0;
	switch( Bike.gravity ) {
		case GRAV_UP: gy = g; break;
		case GRAV_LEFT: gx = -g; break;
		case GRAV_RIGHT: gx = g; break;
		default: gy = -g; break;
	}

	++Bike.steps;
	// Suspension uses the pre-volt velocity, as in erokszamitasa. The rider
	// follows after the volt and must use its new body-point velocity.
	if( Bike.body.omega != oldomega )
		Oms = KMUL32((int32_t)Bike.body.omega,C_OMS);
	rider( gx, gy );

	Bike.body.omega = sat16( (int32_t)Bike.body.omega+dwb );
	Bike.body.vx += dvbx+gx;
	Bike.body.vy += dvby+gy;
	move( &Bike.body );

	for( uint8_t k = 0; k < 2; k++ )
		riding_wheel( &Bike.wheel[k], dvx[k]+gx, dvy[k]+gy, tq[k] );

	// Head collision and rendering use the completed 30 Hz rider pose.
	head_position();
	return !riding_swept_head(riding_sra8(previous_head_x),riding_sra8(previous_head_y),riding_sra8(Bike.head_x),riding_sra8(Bike.head_y));
}

#undef STEP_LOCAL
