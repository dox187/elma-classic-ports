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
#include <stddef.h>
/* Private scheduled suspension workspace; ph_step is non-reentrant. */
typedef struct {
 int16_t cs,sn; int32_t oms;
 wheel_input_t wheel[2];
 int32_t dvbx,dvby,dwb,spring_fraction;
} riding_suspension_state_t;
typedef char suspension_layout[sizeof(riding_suspension_state_t)==52 &&
    offsetof(riding_suspension_state_t,wheel[0])==8 &&
    offsetof(riding_suspension_state_t,wheel[1])==22 &&
    offsetof(riding_suspension_state_t,dvbx)==36 &&
    offsetof(riding_suspension_state_t,spring_fraction)==48 ? 1 : -1];
riding_suspension_state_t riding_suspension_state;
const uint8_t riding_suspension_anchor_x=Q24_ANCHOR_X;
const uint8_t riding_suspension_anchor_y=Q24_ANCHOR_Y;
void riding_suspension_scheduled(void) __sdcccall(0);
void riding_step_fraction(void) __sdcccall(0);
void riding_step_apply(int16_t gravity);
void riding_step_wheels(void) __sdcccall(0);
uint8_t riding_step_head(void);
typedef char scheduled_step_layout[
    sizeof(circle_t)==24 && offsetof(bike_t,body.omega)==20 &&
    offsetof(bike_t,head_x)==88 && offsetof(bike_t,gravity)==97 &&
    GRAV_UP==0 && GRAV_DOWN==1 && GRAV_LEFT==2 && GRAV_RIGHT==3 ? 1 : -1];
#endif

bike_t Bike;
uint8_t riding_subphase;int32_t move_residual[8];
int64_t force_residual[2];
/* Exact sub-unit part of Bike.body.omega, in [-2^23, 2^23). */
int32_t angular_residual;
extern int16_t riding_landing_nx[2], riding_landing_ny[2];
extern uint8_t riding_landing_contact[2];

#ifdef __SDCC
extern int16_t riding_pose_trig[2];
#define Cs riding_pose_trig[0]
#define Sn riding_pose_trig[1]
#define Oms riding_suspension_state.oms
#else
static int16_t Cs, Sn;   // cos and sin of the body's angle
static int32_t Oms;      // body angular velocity, see C_OMS
#endif

#ifndef __SDCC
/* Wheel arms are stored in the position unit, 2^-18 metres. */
typedef struct {
    int32_t relx[2], rely[2], x[2], y[2];
} damping_arms_t;

static int32_t clamp_damping(int64_t value) {
    if (value > INT32_MAX) return INT32_MAX;
    if (value < INT32_MIN) return INT32_MIN;
    return (int32_t)value;
}

static int32_t riding_lever_spin18(int32_t omega, int32_t arm) {
    return clamp_damping(((int64_t)omega * arm + (1L << 17)) >> 18);
}

static int32_t riding_damping_torque18(const damping_arms_t *arms) {
    /* The sum can exceed int64. Preserve each signed product as its integer
     * and fractional parts, then carry the combined fraction exactly once. */
    int64_t units = 0;
    int32_t fraction = 0;
    for (uint8_t k = 0; k < 2; ++k) {
        int64_t x = (int64_t)arms->x[k] * arms->rely[k];
        int64_t y = (int64_t)arms->y[k] * arms->relx[k];
        units += (x >> 18) - (y >> 18);
        fraction += (int32_t)(x & 0x3ffff) - (int32_t)(y & 0x3ffff);
    }
    return clamp_damping(units + (fraction >> 18));
}

static void angle( void ) {
	/* Sample the closest Q16 phase for the suspension anchors. */
	uint16_t a = (uint16_t)((Bike.body.alfa + (1UL << (RIDING_ANGLE_SHIFT-1))) >> RIDING_ANGLE_SHIFT);
	Cs = fcos( a );
	Sn = fsin( a );
}
#endif

/* Rider, renderer and head collision all observe the same completed step. */
#ifdef __SDCC
extern int16_t riding_pose_rest[2];
void riding_step_head_position(void) __sdcccall(0);
void riding_brake_fields(int32_t *left, int32_t *right);
#define head_position riding_step_head_position
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


/* Convert the complete angular velocity to body-point velocity. The second
 * product contributes Q24 units to the first, with a single final rounding. */
#ifdef __SDCC
int32_t body_oms(void) __banked;
#else
static int32_t body_oms(void) {
    int32_t m=q24_C_OMS[riding_subphase];
    int64_t product=(int64_t)Bike.body.omega*m+(((int64_t)angular_residual*m)>>24);
    int64_t result=(product+0x800000L)>>24;
    return result>INT32_MAX ? INT32_MAX : result<INT32_MIN ? INT32_MIN : (int32_t)result;
}
#endif

#ifdef __SDCC
void riding_partial_body_angle(void) __banked;
void riding_full_angle(void) __sdcccall(0);
void riding_body_translate(circle_t *k,uint8_t slot) __sdcccall(0);
#endif

static void move_body(void) {
#ifdef __SDCC
    if (riding_subphase) riding_partial_body_angle();
    else riding_full_angle();
    riding_body_translate(&Bike.body,0);
#else
    int32_t omega=Bike.body.omega;
    uint32_t phase;
    if (!riding_subphase) {
        phase=((uint32_t)omega<<5)+(uint32_t)((angular_residual+0x40000L)>>19);
    } else {
        /* 128 * remainder_time / angular_unit_time = 27007/1280 exactly. */
        int32_t f=(int32_t)(((int64_t)angular_residual*27007)>>24);
        int64_t n=(int64_t)omega*27007+f+640;
        phase=(uint32_t)(n>=0 ? n/1280 : -1-((-1-n)/1280));
    }
    Bike.body.alfa+=phase;
    Bike.body.rx+=phase_advance(Bike.body.vx,2,0);
    Bike.body.ry+=phase_advance(Bike.body.vy,2,1);
#endif
}

// vezeto_hatarolas: keeps the rider over the seat.
#if defined(__SDCC) && defined(RIDING_PC_SCHEDULE)
uint8_t riding_rider_phase_local(int16_t *xy);
#endif
static void rider_limit( void ) {
#if defined(__SDCC) && defined(RIDING_PC_SCHEDULE)
    int16_t xy[2];
    if (riding_rider_phase_local(xy)) return;
    int16_t x = xy[0], y = xy[1];
#else
	int16_t dx = sat16( riding_sra8(Bike.rider_x-Bike.body.rx) );
	int16_t dy = sat16( riding_sra8(Bike.rider_y-Bike.body.ry) );
	int16_t x = dotq14( dx, dy, Cs, Sn );
	int16_t y = dotq14( dy, dx, Cs, -Sn );
#endif
	uint8_t moved = 0;
	if( Bike.turned )
		x = -x;
	int16_t under;
#if RIDING_SEAT_FAST_ENABLED
    under=0;
    if(x>RIDING_SEAT_FAST_X || y<RIDING_SEAT_FAST_Y || y>RIDER_TOP)
#endif
        under=KMUL((int32_t)y-SEAT_Y,C_SEAT_NY)-KMUL((int32_t)x-SEAT_X,C_SEAT_NX);
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
#ifndef __SDCC
static void rider( int32_t gx, int32_t gy ) {
	rider_limit();
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
}
#endif

void ph_init( int32_t x, int32_t y ) {
#ifdef __SDCC
    riding_suspension_state.wheel[0].k=&Bike.wheel[0];
    riding_suspension_state.wheel[1].k=&Bike.wheel[1];
#endif
    angular_residual=0;
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

#ifdef __SDCC
uint8_t riding_recip_index(int16_t,int16_t) __sdcccall(0);
int32_t riding_close_reaction32(int32_t,uint32_t) __sdcccall(0);
#endif

/* The table remains unchanged at ordinary separation. Its first 16 entries
 * flatten close wheel/body compression, so use the exact distance there.
 * The zero-distance case retains the original table fallback. */
int32_t riding_reaction_input32(int32_t tq,int16_t kx,int16_t ky) MATH32_ABI {
#ifdef __SDCC
    uint8_t index=riding_recip_index(kx,ky);
#else
    int16_t x=kx>>4,y=ky>>4;
    if(x>127)x=127;
    if(x< -127)x=-127;
    if(y>127)y=127;
    if(y< -127)y=-127;
    uint16_t d2=(uint16_t)((x*x+y*y)>>5);
    uint8_t index=d2>255?255:(uint8_t)d2;
#endif
    if(index<16) {
        uint32_t distance2=(uint32_t)mul16(kx,kx)+(uint32_t)mul16(ky,ky);
        if(distance2) {
#ifdef __SDCC
            return riding_close_reaction32(tq,distance2);
#else
            int64_t result=(int64_t)tq*4194304/distance2;
            if(result>INT32_MAX)return INT32_MAX;
            if(result<INT32_MIN)return INT32_MIN;
            return (int32_t)result;
#endif
        }
    }
    return riding_mulshift32(tq,Recip_d2[index],8);
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

/* Releases can also change the angular velocity on a substep with no input. */
static void step_volts(uint8_t input) {
	// Volts:
	int32_t oldomega = Bike.body.omega;
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

    if (Bike.body.omega != oldomega) Oms = body_oms();
}

uint8_t ph_step( uint8_t input ) {
#ifndef __SDCC
	int32_t previous_head_x=Bike.head_x,previous_head_y=Bike.head_y;
    angle();
#endif
	Oms = body_oms();

	// Gas and brake:
	uint8_t brake = input & IN_BRAKE;
	if( brake && !Bike.brake_was ) {
		Bike.dbrake[0] = Bike.wheel[0].alfa-Bike.body.alfa;
		Bike.dbrake[1] = Bike.wheel[1].alfa-Bike.body.alfa;
	}
	Bike.brake_was = brake;
#ifdef __SDCC
#define STEP_TORQUE(slot) riding_suspension_state.wheel[slot].tq
#else
    int32_t tq[2];
#define STEP_TORQUE(slot) tq[slot]
#endif
	STEP_TORQUE(0) = 0; STEP_TORQUE(1) = 0;
	if( input & IN_GAS ) {
		if( Bike.turned ) {
			if( Bike.wheel[0].omega > -WHEEL_MAXW )
				STEP_TORQUE(0) = -GAS_TQ;
		}
		else if( Bike.wheel[1].omega < WHEEL_MAXW )
			STEP_TORQUE(1) = GAS_TQ;
	}
	if( brake ) {
#ifdef __SDCC
        riding_brake_fields(&STEP_TORQUE(0), &STEP_TORQUE(1));
#else
		for( uint8_t k = 0; k < 2; k++ ) {
			// Brake deflection accumulates: wrapping at half a turn reverses
			// the spring torque during hard landings (Hi Flyer's final pipe).
			int32_t da = riding_sra8((int32_t)(Bike.wheel[k].alfa-(Bike.body.alfa+Bike.dbrake[k])));
			/* da is signed24 after >>8; its uint8-factor product and round
             * fit signed32, so this is exact and avoids generic long multiply. */
            int32_t spring = KMUL32(da,C_BRAKE_A);
			int32_t dw = Bike.wheel[k].omega-Bike.body.omega;
			tq[k] = -spring-(riding_landing_contact[k]?KMUL32(dw,C_BRAKE_GW):KMUL32(dw,C_BRAKE_W));
		}
#endif
	}

#undef STEP_TORQUE
#ifdef __SDCC
    riding_suspension_scheduled();
    riding_step_fraction();
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
	STEP_LOCAL damping_arms_t damping;
	for( uint8_t k = 0; k < 2; k++ ) {
		circle_t* w = &Bike.wheel[k];
        int32_t gx = Bike.body.rx-w->rx+gsx[k];
        int32_t gy = Bike.body.ry-w->ry+gsy[k];
		dvx[k] = Q24_MUL(gx,C_SPRING_FW);riding_force_sub(0,dvx[k],q24_fraction);
		dvy[k] = Q24_MUL(gy,C_SPRING_FW);riding_force_sub(1,dvy[k],q24_fraction);
		ts += riding_spring_torque32(gsx[k],gsy[k],gx,gy);

        int32_t lx = (int32_t)((uint32_t)w->rx - (uint32_t)Bike.body.rx);
        int32_t ly = (int32_t)((uint32_t)w->ry - (uint32_t)Bike.body.ry);
        int16_t kx = sat16((lx >> 8) + ((lx >> 7) & 1));
        int16_t ky = sat16((ly >> 8) + ((ly >> 7) & 1));
        // The velocity of the body at the wheel against the wheel's:
        int32_t relx = (int32_t)((uint32_t)Bike.body.vx - (uint32_t)w->vx
                                 - (uint32_t)riding_lever_spin18(Oms, ly));
        int32_t rely = (int32_t)((uint32_t)Bike.body.vy - (uint32_t)w->vy
                                 + (uint32_t)riding_lever_spin18(Oms, lx));
		int32_t dfx=KMUL32(relx,C_FRIC_W);riding_force_sub(0,dfx,q24_fraction);dvx[k]+=dfx;
		int32_t dfy=KMUL32(rely,C_FRIC_W);riding_force_sub(1,dfy,q24_fraction);dvy[k]+=dfy;
		damping.x[k]=lx;damping.y[k]=ly;
        damping.relx[k]=relx;damping.rely[k]=rely;
        int32_t olddvx=dvx[k],olddvy=dvy[k];

		if( tq[k] ) {
			int32_t tr = KMUL32(riding_reaction_input32(tq[k],kx,ky),C_REACT);
			dvx[k] += riding_mulq32(tr,ky,14);
			dvy[k] -= riding_mulq32(tr,kx,14);
 riding_force_sub(0,dvx[k]-olddvx,0);riding_force_sub(1,dvy[k]-olddvy,0);
		}
	}
	// The body gets all the forces between them, of the opposite sign, with
	// 20 times the mass of a wheel:
    int32_t dvbx=riding_force_finish(0);
    int32_t dvby=riding_force_finish(1);
	/* Round the combined spring moment. Flooring two cancelling wheel
     * contributions can otherwise accumulate a pitch impulse on level ground. */
    int32_t spring_input = (riding_sra8(ts) >> 2) + ((ts >> 9) & 1);
    int32_t dwb = -KMUL32(spring_input,C_SPRING_T);
	int32_t spring_fraction=q24_fraction;
	dwb-=KMUL32(riding_damping_torque18(&damping),C_FRIC_T);


    /* Both torque products are subtracted. Keep the old residual available
     * to the rider until the body receives this substep's angular impulse. */
    int32_t next_fraction=angular_residual-spring_fraction-q24_fraction;
    int8_t angular_carry=(int8_t)((next_fraction+0x800000L)>>24);
    next_fraction-=(int32_t)angular_carry*0x1000000L;
    dwb+=angular_carry;
#endif

    if ((input & (IN_VOLT_RIGHT | IN_VOLT_LEFT)) || Bike.volt[0] || Bike.volt[1])
        step_volts(input);

	// Gravity, with its fraction carried over:
	int16_t g = G_INT;
	uint8_t f = Bike.gfrac;
	Bike.gfrac = f+G_FRAC;
	if( Bike.gfrac < f )
		g++;
    ++Bike.steps;
#ifdef __SDCC
    rider_limit();
    riding_step_apply(g);
    move_body();
    riding_step_wheels();
    return riding_step_head();
#else
	int16_t gx = 0, gy = 0;
	switch( Bike.gravity ) {
		case GRAV_UP: gy = g; break;
		case GRAV_LEFT: gx = -g; break;
		case GRAV_RIGHT: gx = g; break;
		default: gy = -g; break;
	}

	rider( gx, gy );

	Bike.body.omega += dwb;
    angular_residual=next_fraction;
	Bike.body.vx += dvbx+gx;
	Bike.body.vy += dvby+gy;
	move_body();

	for( uint8_t k = 0; k < 2; k++ )
		riding_wheel( &Bike.wheel[k], dvx[k]+gx, dvy[k]+gy, tq[k] );

	// Head collision and rendering use the completed 30 Hz rider pose.
	head_position();
	return !riding_swept_head(riding_sra8(previous_head_x),riding_sra8(previous_head_y),riding_sra8(Bike.head_x),riding_sra8(Bike.head_y));
#endif
}

#undef STEP_LOCAL
