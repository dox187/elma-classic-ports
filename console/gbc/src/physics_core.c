#ifdef __SDCC
#pragma bank 8
#endif
// Fixed-point dynamics adapted from the NES C reference, with GBC clock
// constants and exact host implementations of the SM83 arithmetic helpers.
#include "physics_core.h"
#include "physics_math.h"
#include "physics_math32.h"
#include "physics_force.h"
#include "physics_spring_torque.h"
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

#ifdef __SDCC
/* Private scheduled suspension workspace; ph_step is non-reentrant. */
typedef struct {
 int16_t cs,sn; int32_t oms; int16_t tq[2];
 int32_t dvx[2],dvy[2],dvbx,dvby,dwb;
} riding_suspension_state_t;
riding_suspension_state_t riding_suspension_state;
const uint8_t riding_suspension_anchor_x=Q24_ANCHOR_X;
const uint8_t riding_suspension_anchor_y=Q24_ANCHOR_Y;
void riding_suspension_scheduled(void) __sdcccall(0);
#endif

bike_t Bike;
uint8_t riding_subphase;int32_t move_residual[8];
int64_t force_residual[2];
extern int16_t riding_landing_nx[2], riding_landing_ny[2];
extern uint8_t riding_landing_contact[2];

static int16_t Cs, Sn;   // cos and sin of the body's angle
static int32_t Oms;      // body angular velocity, see C_OMS

#ifndef __SDCC
static void angle( void ) {
	uint16_t a = (uint16_t)(Bike.body.alfa >> RIDING_ANGLE_SHIFT);
	Cs = fcos( a );
	Sn = fsin( a );
}
#endif

/* Rider, renderer and head collision all observe the same completed step. */
#ifdef __SDCC
void riding_head_pose32(int16_t*,int16_t*) __sdcccall(0);
void riding_brake32(int16_t*) __sdcccall(0);
static void head_position(void) {riding_head_pose32(&Cs,&Sn);}
#else
static void head_position(void) {
 int32_t x=Bike.rider_x,y=Bike.rider_y;
 int16_t hc,hs;
 angle();hc=KMUL(Cs,C_H_X);hs=KMUL(Sn,C_H_X);
 if(!Bike.turned){hc=-hc;hs=-hs;}
 Bike.head_x=x+(int32_t)(hc-KMUL(Sn,C_H_Y))*256L;
 Bike.head_y=y+(int32_t)(hs+KMUL(Cs,C_H_Y))*256L;
}
#endif


static void move(circle_t *k) {
 k->alfa += (uint32_t)(phase_move(k->omega,7));
 k->rx += phase_advance(k->vx,2,k==&Bike.body?0:k==&Bike.wheel[0]?2:4);
 k->ry += phase_advance(k->vy,2,k==&Bike.body?1:k==&Bike.wheel[0]?3:5);
}

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
#ifdef __SDCC
void riding_rider_response32(int16_t,int16_t,int32_t,int32_t,int32_t) __sdcccall(0);
#endif
static void rider( int32_t gx, int32_t gy ) {
	rider_limit();
#ifdef __SDCC
 riding_rider_response32(-KMUL(Sn,C_RREST),KMUL(Cs,C_RREST),Oms,gx,gy);
#else
	int16_t dirx = sat16( ((Bike.body.rx-Bike.rider_x) >> 4)-KMUL( Sn, C_RREST ) );
	int16_t diry = sat16( ((Bike.body.ry-Bike.rider_y) >> 4)+KMUL( Cs, C_RREST ) );
	int16_t dx = sat16( (Bike.rider_x-Bike.body.rx) >> 4 );
	int16_t dy = sat16( (Bike.rider_y-Bike.body.ry) >> 4 );
	// The velocity of the body there:
	int32_t relx = Bike.rider_vx-(Bike.body.vx+riding_mulq32(Oms,-dy,14));
	int32_t rely = Bike.rider_vy-(Bike.body.vy+riding_mulq32(Oms,dx,14));
	int32_t ax = KMUL32(dirx,C_RIDER_S)-KMUL32(relx,C_RIDER_F)+gx;
	int32_t ay = KMUL32(diry,C_RIDER_S)-KMUL32(rely,C_RIDER_F)+gy;
	Bike.rider_vx += ax;
	Bike.rider_vy += ay;
	Bike.rider_x += phase_advance(Bike.rider_vx,2,6);
	Bike.rider_y += phase_advance(Bike.rider_vy,2,7);
#endif
}

void ph_init( int32_t x, int32_t y ) {
	uint8_t* p = (uint8_t*)&Bike;
	for( uint16_t i = 0; i < sizeof( bike_t ); i++ )
		p[i] = 0;
	Bike.gravity = GRAV_DOWN;for(uint8_t j=0;j<8;++j)move_residual[j]=0;force_residual[0]=force_residual[1]=0;
    riding_landing_nx[0]=riding_landing_nx[1]=0;
    riding_landing_ny[0]=riding_landing_ny[1]=0;
    riding_landing_contact[0]=riding_landing_contact[1]=0;
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
const int16_t Recip_d2[] = {
#include "../../nes/src/recip.inc"
};

static int16_t clamp_w( int32_t w ) {
	if( w > 16383 ) return 16383;
	if( w < -16383 ) return -16383;
	return (int16_t)w;
}

/* ph_step follows the single global Bike and is never called by interrupts.
 * Give its arrays fixed SM83 addresses; HOST keeps automatic storage. */
#ifdef __SDCC
#define STEP_LOCAL static
#else
#define STEP_LOCAL
#endif

/* A supported wheel constrains normal motion. The damper then accelerates
 * the body point, whose effective mass includes body pitch, instead of the
 * free 10 kg wheel. Correct only the body reaction: wheel release and tangent
 * response retain their existing impulses. The previous resolved contacts
 * are used, so support changes have one simulation step of latency.
 * Two retained contacts constrain both dimensions; a single contact uses its
 * original Q14 normal (including normalization rounding at merged vertices).
 */
#if RIDING_EXPONENTIAL_DAMPER
static void landing_response(riding_torque32_t *t,int32_t *sx,int32_t *sy) {
    for(uint8_t k=0;k<2;++k) {
        int32_t x,y,extra;
        int16_t nx=riding_landing_nx[k],ny=riding_landing_ny[k];
        if(!riding_landing_contact[k])continue;
        x=t->relx[k];y=t->rely[k];
        if(riding_landing_contact[k]==2) {
            x+=KMUL32(x,C_LANDING_EXTRA);
            y+=KMUL32(y,C_LANDING_EXTRA);
        } else if(nx==0 && (ny==16384 || ny==-16384)) {
            extra=KMUL32(ny>0?y:-y,C_LANDING_EXTRA);
            y+=ny>0?extra:-extra;
        } else if(ny==0 && (nx==16384 || nx==-16384)) {
            extra=KMUL32(nx>0?x:-x,C_LANDING_EXTRA);
            x+=nx>0?extra:-extra;
        } else {
            extra=KMUL32(riding_dotq32(x,y,nx,ny,14),C_LANDING_EXTRA);
            x+=riding_mulq32(extra,nx,14);
            y+=riding_mulq32(extra,ny,14);
        }
        /* Preserve the rounding of each original damper impulse. */
        if(x!=t->relx[k]) {
            *sx+=KMUL32(x,C_FRIC_W)-KMUL32(t->relx[k],C_FRIC_W);
            t->relx[k]=x;
        }
        if(y!=t->rely[k]) {
            *sy+=KMUL32(y,C_FRIC_W)-KMUL32(t->rely[k],C_FRIC_W);
            t->rely[k]=y;
        }
    }
}
#endif

uint8_t ph_step( uint8_t input ) {
	int32_t previous_head_x=Bike.head_x,previous_head_y=Bike.head_y;
#ifndef __SDCC
    angle();
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
#ifdef __SDCC
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
			tq[k] = sat16( -spring-(riding_landing_contact[k]?KMUL(dw,C_BRAKE_GW):KMUL(dw,C_BRAKE_W)) );
		}
#endif
	}

#ifdef __SDCC
 riding_suspension_state.cs=Cs;riding_suspension_state.sn=Sn;
 riding_suspension_state.oms=Oms;
 riding_suspension_state.tq[0]=tq[0];riding_suspension_state.tq[1]=tq[1];
 riding_suspension_scheduled();
 int32_t *dvx=riding_suspension_state.dvx,*dvy=riding_suspension_state.dvy;
 int32_t dvbx=riding_suspension_state.dvbx,dvby=riding_suspension_state.dvby;
 int32_t dwb=riding_suspension_state.dwb;
#else
	// Forces between the wheels and the body (erokszamitasa). The anchors
	// of the springs, from the rotation of (K_X, -K_Y):
	int32_t a = q24_apply(Cs,Q24_ANCHOR_X), b = q24_apply(Sn,Q24_ANCHOR_Y);
	int32_t c = q24_apply(Sn,Q24_ANCHOR_X), d = q24_apply(Cs,Q24_ANCHOR_Y);
	STEP_LOCAL int32_t gsx[2], gsy[2];
	gsx[1] = a+b;
	gsy[1] = c-d;
	gsx[0] = b-a;
	gsy[0] = -c-d;

	STEP_LOCAL int32_t dvx[2], dvy[2];
	int32_t ts = 0;
    riding_force_begin();
	STEP_LOCAL riding_torque32_t damping;
	for( uint8_t k = 0; k < 2; k++ ) {
		circle_t* w = &Bike.wheel[k];
        int32_t gx = Bike.body.rx-w->rx+gsx[k];
        int32_t gy = Bike.body.ry-w->ry+gsy[k];
		dvx[k] = Q24_MUL(gx,C_SPRING_FW);riding_force_sub(0,dvx[k],q24_fraction);
		dvy[k] = Q24_MUL(gy,C_SPRING_FW);riding_force_sub(1,dvy[k],q24_fraction);
		ts += riding_spring_torque32(gsx[k],gsy[k],gx,gy);

        int16_t kx = sat16( riding_sra8(w->rx-Bike.body.rx+128) );
        int16_t ky = sat16( riding_sra8(w->ry-Bike.body.ry+128) );
		// The velocity of the body at the wheel against the wheel's:
		int32_t relx = Bike.body.vx-w->vx-riding_mulq32(Oms,ky,10);
		int32_t rely = Bike.body.vy-w->vy+riding_mulq32(Oms,kx,10);
		int32_t dfx=KMUL32(relx,C_FRIC_W);riding_force_sub(0,dfx,q24_fraction);dvx[k]+=dfx;
		int32_t dfy=KMUL32(rely,C_FRIC_W);riding_force_sub(1,dfy,q24_fraction);dvy[k]+=dfy;
		damping.kx[k]=kx;damping.ky[k]=ky;
        damping.relx[k]=relx;damping.rely[k]=rely;
        int32_t olddvx=dvx[k],olddvy=dvy[k];

		if( tq[k] ) {
			// 1/d^2 from a table, with d^2 from the high bits of k:
            int16_t kx8 = kx >> 4, ky8 = ky >> 4;
			if( kx8 > 127 ) kx8 = 127;
			if( kx8 < -127 ) kx8 = -127;
			if( ky8 > 127 ) ky8 = 127;
			if( ky8 < -127 ) ky8 = -127;
			uint16_t d2 = (uint16_t)((kx8*kx8 + ky8*ky8) >> 5);
            int16_t rec = Recip_d2[d2 > 255 ? 255 : d2];
			int32_t tr = KMUL32(riding_mulshift32((int32_t)tq[k],rec,8),C_REACT);
			dvx[k] += riding_mulq32(tr,ky,14);
			dvy[k] -= riding_mulq32(tr,kx,14);
 riding_force_sub(0,dvx[k]-olddvx,0);riding_force_sub(1,dvy[k]-olddvy,0);
		}
	}
	// The body gets all the forces between them, of the opposite sign, with
	// 20 times the mass of a wheel:
    int32_t dvbx=riding_force_finish(0);
    int32_t dvby=riding_force_finish(1);
	int32_t dwb = -(int32_t)KMUL(sat16(riding_sra8(ts)>>2),C_SPRING_T)
	              -KMUL32(riding_torque_input32(&damping),C_FRIC_T);

#endif

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
