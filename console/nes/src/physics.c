// The physics in C: the description of what physics.s does on the NES,
// to the bit, and the physics of the tests on the host.
#include "physics.h"
#include "fixmath.h"
#include "physconst.h"

bike_t Bike;

// Wheel torques are in units of 1/4 Nm. The constants are in physconst.h.
typedef struct {
	int16_t nx, ny;  // from the contact point to the center, 16384 is 1
	int16_t l;       // distance of the center, u
	int16_t tx, ty;  // the contact point, u from the origin of the lines
} contact_t;

static contact_t Ct[2];
static int16_t Cs, Sn;   // cos and sin of the body's angle
static int16_t Oms;      // body angular velocity, see C_OMS

static void angle( void ) {
	uint16_t a = (uint16_t)(Bike.body.alfa >> 8);
	Cs = fcos( a );
	Sn = fsin( a );
}

// 2^18/sqrt( d2 ) for d2 in steps of 512 u^2 from 16384 u^2:
static const int16_t Rsqrt[] = {
#include "rsqrt.inc"
};

// Unit vector and length of a short vector in u, d2 its length squared:
static void normalize( int16_t dx, int16_t dy, int32_t d2, contact_t* c ) {
	if( d2 < 16384 ) {
		// Deep in the ground, rare:
		int16_t l = (int16_t)isqrt32( (uint32_t)d2 );
		if( l == 0 ) {
			c->nx = 0;
			c->ny = 16384;
			c->l = 0;
			return;
		}
		c->nx = (int16_t)(((int32_t)dx << 14)/l);
		c->ny = (int16_t)(((int32_t)dy << 14)/l);
		c->l = l;
		return;
	}
	uint16_t i = (uint16_t)((d2-16384) >> 9);
	if( i >= sizeof( Rsqrt )/sizeof( Rsqrt[0] ) )
		i = sizeof( Rsqrt )/sizeof( Rsqrt[0] )-1;
	int16_t r = Rsqrt[i];
	c->nx = sat16( mul16( dx, r ) >> 4 );
	c->ny = sat16( mul16( dy, r ) >> 4 );
	c->l = dotq14( c->nx, c->ny, dx, dy );
}

static void contact_point( contact_t* c, int16_t qx, int16_t qy ) {
	c->tx = qx-mulq14( c->nx, c->l );
	c->ty = qy-mulq14( c->ny, c->l );
}

// talppontkereses of UTKOZES.CPP: at most two contact points of the wheel
// with its center at cx, cy (u).
static uint8_t contacts( int32_t cx, int32_t cy ) {
	uint8_t found = 0;
	const seg_t* s;
	seg_query( seg_cell( cx ), seg_cell( cy ) );
	int16_t qx = (int16_t)(cx & 4095), qy = (int16_t)(cy & 4095);
	uint8_t bx = SEG_BOX( qx ), by = SEG_BOX( qy );
	while( (s = seg_next()) ) {
		if( bx < s->x0 || bx > s->x1 || by < s->y0 || by > s->y1 )
			continue;
		int16_t x = qx-s->px, y = qy-s->py;
		int16_t d = dotq14( x, y, -s->ey, s->ex );
		if( d >= R_WHEEL || d <= -R_WHEEL )
			continue;
		int16_t pos = dotq14( x, y, s->ex, s->ey );
		contact_t* k = &Ct[found];
		if( pos >= 0 && pos <= s->len ) {
			if( d >= 0 ) {
				k->nx = -s->ey;
				k->ny = s->ex;
				k->l = d;
			}
			else {
				k->nx = s->ey;
				k->ny = -s->ex;
				k->l = -d;
			}
		}
		else {
			// Near an end point:
			if( pos > 0 ) {
				x -= s->dx;
				y -= s->dy;
			}
			if( x >= R_WHEEL || x <= -R_WHEEL || y >= R_WHEEL || y <= -R_WHEEL )
				continue;
			int32_t d2 = mul16( x, x )+mul16( y, y );
			if( d2 >= (int32_t)R_WHEEL*R_WHEEL )
				continue;
			normalize( x, y, d2, k );
		}
		if( found == 0 ) {
			found = 1;
			continue;
		}
		contact_point( &Ct[0], qx, qy );
		contact_point( &Ct[1], qx, qy );
		int16_t dx = Ct[1].tx-Ct[0].tx, dy = Ct[1].ty-Ct[0].ty;
		if( dx < MERGE && dx > -MERGE && dy < MERGE && dy > -MERGE &&
				mul16( dx, dx )+mul16( dy, dy ) < (int32_t)MERGE*MERGE ) {
			// Merged into their average:
			int16_t ax = qx-Ct[0].tx-(dx >> 1);
			int16_t ay = qy-Ct[0].ty-(dy >> 1);
			normalize( ax, ay, mul16( ax, ax )+mul16( ay, ay ), &Ct[0] );
		}
		else
			return 2;
	}
	return found;
}

// Whether a circle at cx, cy (u) touches the ground:
static uint8_t touches( int32_t cx, int32_t cy, int16_t rad ) {
	const seg_t* s;
	seg_query( seg_cell( cx ), seg_cell( cy ) );
	int16_t qx = (int16_t)(cx & 4095), qy = (int16_t)(cy & 4095);
	uint8_t bx = SEG_BOX( qx ), by = SEG_BOX( qy );
	while( (s = seg_next()) ) {
		// The box is larger by the radius of a wheel, more than rad:
		if( bx < s->x0 || bx > s->x1 || by < s->y0 || by > s->y1 )
			continue;
		int16_t x = qx-s->px, y = qy-s->py;
		int16_t d = dotq14( x, y, -s->ey, s->ex );
		if( d >= rad || d <= -rad )
			continue;
		int16_t pos = dotq14( x, y, s->ex, s->ey );
		if( pos >= 0 && pos <= s->len )
			return 1;
		if( pos > 0 ) {
			x -= s->dx;
			y -= s->dy;
		}
		if( mul16( x, x )+mul16( y, y ) < (int32_t)rad*rad )
			return 1;
	}
	return 0;
}

// helyigazitas: does not let the wheel into the ground deeper than the band.
// The other contact point gets farther by the push along its direction.
static void pushout( circle_t* k, contact_t* c, contact_t* other ) {
	int16_t push = R_WHEEL-BAND-c->l;
	if( push <= 0 )
		return;
	int16_t px = mulq14( push, c->nx ), py = mulq14( push, c->ny );
	k->rx += (int32_t)px << 8;
	k->ry += (int32_t)py << 8;
	c->l += push;
	if( other )
		other->l += dotq14( px, py, other->nx, other->ny );
}

// talppontigazitas: true if the point really supports the wheel. With two
// points, the velocity towards it is removed (with one, rolling around it
// takes only the velocity along the ground anyway).
static uint8_t supports( circle_t* k, const contact_t* c, int16_t dvx, int16_t dvy,
						 uint8_t remove ) {
	int16_t nv = dotq14( k->vx, k->vy, c->nx, c->ny );
	if( nv > -ELSZ && dotq14( dvx, dvy, c->nx, c->ny ) > 0 )
		return 0;
	if( remove ) {
		k->vx -= mulq14( nv, c->nx );
		k->vy -= mulq14( nv, c->ny );
	}
	return 1;
}

static uint8_t same_side( int32_t d, int32_t m ) {
	return !((d < 0 && m > 0) || (d > 0 && m < 0));
}

// biztostalppont_uj: true if the wheel stays on t1 turning around t2.
static uint8_t sure_new( const contact_t* t1, const contact_t* t2, const circle_t* k ) {
	int16_t vn = dotq14( k->vx, k->vy, -t2->ny, t2->nx );
	int16_t m = k->omega + KMUL( sat16( mul16( t2->l, vn ) >> 10 ), C_NEW );
	int16_t d = dotq14( t1->tx-t2->tx, t1->ty-t2->ty, -t2->ny, t2->nx );
	return same_side( d, m );
}

// biztostalppont_regi:
static uint8_t sure_old( const contact_t* t1, const contact_t* t2,
						 int16_t dvx, int16_t dvy, int16_t tq ) {
	int16_t dvn = dotq14( dvx, dvy, -t2->ny, t2->nx );
	int16_t p = sat16( mul16( t2->l, dvn ) >> 6 );
	int32_t m = (int32_t)tq + KMUL( p, C_OLD );
	int16_t d = dotq14( t1->tx-t2->tx, t1->ty-t2->ty, -t2->ny, t2->nx );
	return same_side( d, m );
}

static uint8_t faster_1ms( const circle_t* k ) {
	if( k->vx >= VEL_1MS || k->vx <= -VEL_1MS || k->vy >= VEL_1MS || k->vy <= -VEL_1MS )
		return 1;
	return mul16( k->vx, k->vx )+mul16( k->vy, k->vy ) > (int32_t)VEL_1MS*VEL_1MS;
}

static void move( circle_t* k ) {
	k->alfa += (int32_t)k->omega << 7;
	k->rx += (int32_t)k->vx << 2;
	k->ry += (int32_t)k->vy << 2;
}

// beallit for a wheel: dv is the velocity change from the forces, tq the
// torque on it.
static void wheel( circle_t* k, int16_t dvx, int16_t dvy, int16_t tq ) {
	uint8_t n = contacts( k->rx >> 8, k->ry >> 8 );
	uint8_t two = n == 2;
	if( n > 0 )
		pushout( k, &Ct[0], two ? &Ct[1] : 0 );
	if( two ) {
		pushout( k, &Ct[1], 0 );
		if( faster_1ms( k ) ) {
			if( !sure_new( &Ct[0], &Ct[1], k ) ) {
				n = 1;
				Ct[0] = Ct[1];
			}
			else if( !sure_new( &Ct[1], &Ct[0], k ) )
				n = 1;
		}
		else {
			if( !sure_old( &Ct[0], &Ct[1], dvx, dvy, tq ) ) {
				n = 1;
				Ct[0] = Ct[1];
			}
			else if( !sure_old( &Ct[1], &Ct[0], dvx, dvy, tq ) )
				n = 1;
		}
		if( n == 2 && !supports( k, &Ct[1], dvx, dvy, 1 ) )
			n = 1;
	}
	if( n >= 1 && !supports( k, &Ct[0], dvx, dvy, two ) ) {
		if( n == 2 ) {
			n = 1;
			Ct[0] = Ct[1];
		}
		else
			n = 0;
	}
	if( n == 0 ) {
		k->omega += KMUL( tq, C_FREE );
		k->vx += dvx;
		k->vy += dvy;
		move( k );
		return;
	}
	if( n == 2 ) {
		k->vx = k->vy = 0;
		k->omega = 0;
		return;
	}
	// Rolls around the contact point:
	int16_t n90x = -Ct[0].ny, n90y = Ct[0].nx;
	int16_t vn = dotq14( k->vx, k->vy, n90x, n90y );
	int16_t dvn = dotq14( dvx, dvy, n90x, n90y );
	int16_t t = sat16( (int32_t)tq + KMUL( dvn, C_ROLL_T ) );
	int16_t w = KMUL( vn, C_ROLL_W )+KMUL( t, C_ROLL_DW );
	k->omega = w;
	int16_t sp = KMUL( w, C_ROLL_V );
	k->vx = mulq14( sp, n90x );
	k->vy = mulq14( sp, n90y );
	move( k );
}

// vezeto_hatarolas: keeps the rider over the seat.
static void rider_limit( void ) {
	int16_t dx = sat16( (Bike.rider_x-Bike.body.rx) >> 8 );
	int16_t dy = sat16( (Bike.rider_y-Bike.body.ry) >> 8 );
	int16_t x = dotq14( dx, dy, Cs, Sn );
	int16_t y = dotq14( dy, dx, Cs, -Sn );
	uint8_t moved = 0;
	if( Bike.turned )
		x = -x;
	int16_t under = KMUL( y-SEAT_Y, C_SEAT_NY )-KMUL( x-SEAT_X, C_SEAT_NX );
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
	if( x > 0 && y > 0 ) {
		int16_t xs = KMUL( x, C_ELLIPSE );
		int32_t d2 = mul16( xs, xs )+mul16( y, y );
		if( d2 > (int32_t)RIDER_TOP*RIDER_TOP ) {
			int16_t d = (int16_t)isqrt32( (uint32_t)d2 );
			x = (int16_t)(mul16( x, RIDER_TOP )/d);
			y = (int16_t)(mul16( y, RIDER_TOP )/d);
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

// beallitvezeto, for two steps:
static void rider( int16_t gx, int16_t gy ) {
	rider_limit();
	int16_t dirx = sat16( ((Bike.body.rx-Bike.rider_x) >> 4)-KMUL( Sn, C_RREST ) );
	int16_t diry = sat16( ((Bike.body.ry-Bike.rider_y) >> 4)+KMUL( Cs, C_RREST ) );
	int16_t dx = sat16( (Bike.rider_x-Bike.body.rx) >> 4 );
	int16_t dy = sat16( (Bike.rider_y-Bike.body.ry) >> 4 );
	// The velocity of the body there:
	int16_t relx = Bike.rider_vx-(Bike.body.vx+mulq14( -dy, Oms ));
	int16_t rely = Bike.rider_vy-(Bike.body.vy+mulq14( dx, Oms ));
	Bike.rider_vx += KMUL( dirx, C_RIDER_S )-KMUL( relx, C_RIDER_F )+gx;
	Bike.rider_vy += KMUL( diry, C_RIDER_S )-KMUL( rely, C_RIDER_F )+gy;
	Bike.rider_x += (int32_t)Bike.rider_vx << 3;
	Bike.rider_y += (int32_t)Bike.rider_vy << 3;
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
}

void ph_turn( void ) {
	Bike.turned = !Bike.turned;
}

// 2^30/d^2 for d^2 in steps of 2^13 u^2 (distances below 0.36 m count as
// 0.36 m):
static const int16_t Recip_d2[] = {
#include "recip.inc"
};

static int16_t clamp_w( int16_t w ) {
	if( w > 16383 ) return 16383;
	if( w < -16383 ) return -16383;
	return w;
}

uint8_t ph_step( uint8_t input ) {
	angle();
	Oms = KMUL( Bike.body.omega, C_OMS );

	// Gas and brake:
	uint8_t brake = input & IN_BRAKE;
	if( brake && !Bike.brake_was ) {
		Bike.dbrake[0] = Bike.wheel[0].alfa-Bike.body.alfa;
		Bike.dbrake[1] = Bike.wheel[1].alfa-Bike.body.alfa;
	}
	Bike.brake_was = brake;
	int16_t tq[2] = { 0, 0 };
	if( input & IN_GAS ) {
		if( Bike.turned ) {
			if( Bike.wheel[0].omega > -WHEEL_MAXW )
				tq[0] = -GAS_TQ;
		}
		else if( Bike.wheel[1].omega < WHEEL_MAXW )
			tq[1] = GAS_TQ;
	}
	if( brake ) {
		for( uint8_t k = 0; k < 2; k++ ) {
			// Brake deflection accumulates: wrapping at half a turn reverses
			// the spring torque during hard landings (Hi Flyer's final pipe).
			int32_t da = (int32_t)(Bike.wheel[k].alfa-(Bike.body.alfa+Bike.dbrake[k])) >> 8;
			int32_t spring = (da*C_BRAKE_A_M+(1L << (C_BRAKE_A_E-1))) >> C_BRAKE_A_E;
			int16_t dw = clamp_w( Bike.wheel[k].omega-Bike.body.omega );
			tq[k] = sat16( -spring-KMUL( dw, C_BRAKE_W ) );
		}
	}

	// Forces between the wheels and the body (erokszamitasa). The anchors
	// of the springs, from the rotation of (K_X, -K_Y):
	int16_t a = KMUL( Cs, C_K_X ), b = KMUL( Sn, C_K_Y );
	int16_t c = KMUL( Sn, C_K_X ), d = KMUL( Cs, C_K_Y );
	int16_t gsx[2], gsy[2];
	gsx[1] = a+b;
	gsy[1] = c-d;
	gsx[0] = b-a;
	gsy[0] = -c-d;

	int16_t dvx[2], dvy[2];
	int32_t ts = 0, tf = 0;
	for( uint8_t k = 0; k < 2; k++ ) {
		circle_t* w = &Bike.wheel[k];
		int16_t gx = sat16( ((Bike.body.rx-w->rx) >> 4)+((int32_t)gsx[k] << 4) );
		int16_t gy = sat16( ((Bike.body.ry-w->ry) >> 4)+((int32_t)gsy[k] << 4) );
		dvx[k] = KMUL( gx, C_SPRING_W );
		dvy[k] = KMUL( gy, C_SPRING_W );
		ts += mul16( gsx[k], gy )-mul16( gsy[k], gx );

		int16_t kx = sat16( (w->rx-Bike.body.rx) >> 8 );
		int16_t ky = sat16( (w->ry-Bike.body.ry) >> 8 );
		// The velocity of the body at the wheel against the wheel's:
		int16_t relx = sat16( (int32_t)Bike.body.vx-w->vx-mulq10( ky, Oms ) );
		int16_t rely = sat16( (int32_t)Bike.body.vy-w->vy+mulq10( kx, Oms ) );
		dvx[k] += KMUL( relx, C_FRIC_W );
		dvy[k] += KMUL( rely, C_FRIC_W );
		tf += mul16( kx, rely )-mul16( ky, relx );

		if( tq[k] ) {
			// 1/d^2 from a table, with d^2 from the high bits of k:
			int16_t kx8 = kx >> 4, ky8 = ky >> 4;
			if( kx8 > 127 ) kx8 = 127;
			if( kx8 < -127 ) kx8 = -127;
			if( ky8 > 127 ) ky8 = 127;
			if( ky8 < -127 ) ky8 = -127;
			uint16_t d2 = (uint16_t)((kx8*kx8 + ky8*ky8) >> 5);
			int16_t rec = Recip_d2[d2 > 255 ? 255 : d2];
			int16_t tr = KMUL( sat16( mul16( tq[k], rec ) >> 8 ), C_REACT );
			dvx[k] += mulq14( ky, tr );
			dvy[k] -= mulq14( kx, tr );
		}
	}
	// The body gets all the forces between them, of the opposite sign, with
	// 20 times the mass of a wheel:
	int16_t dvbx = -KMUL( sat16( (int32_t)dvx[0]+dvx[1] ), C_TWENTIETH );
	int16_t dvby = -KMUL( sat16( (int32_t)dvy[0]+dvy[1] ), C_TWENTIETH );
	int16_t dwb = -KMUL( sat16( ts >> 10 ), C_SPRING_T )-KMUL( sat16( tf >> 10 ), C_FRIC_T );

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
		int16_t dw = KMUL( Bike.body.omega-oldomega, C_OMS );
		int16_t dx = sat16( (Bike.rider_x-Bike.body.rx) >> 4 );
		int16_t dy = sat16( (Bike.rider_y-Bike.body.ry) >> 4 );
		Bike.rider_vx += mulq14( -dy, dw );
		Bike.rider_vy += mulq14( dx, dw );
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

	uint8_t odd = ++Bike.steps & 1;
	if( odd )
		rider( gx << 1, gy << 1 );

	Bike.body.omega = sat16( (int32_t)Bike.body.omega+dwb );
	Bike.body.vx += dvbx+gx;
	Bike.body.vy += dvby+gy;
	move( &Bike.body );

	for( uint8_t k = 0; k < 2; k++ )
		wheel( &Bike.wheel[k], dvx[k]+gx, dvy[k]+gy, tq[k] );

	// The head (szamitfejr), checked every other step:
	if( odd )
		return 1;
	angle();
	int16_t hc = KMUL( Cs, C_H_X ), hs = KMUL( Sn, C_H_X );
	if( !Bike.turned ) {
		hc = -hc;
		hs = -hs;
	}
	Bike.head_x = Bike.rider_x + ((int32_t)(hc-KMUL( Sn, C_H_Y )) << 8);
	Bike.head_y = Bike.rider_y + ((int32_t)(hs+KMUL( Cs, C_H_Y )) << 8);
	return !touches( Bike.head_x >> 8, Bike.head_y >> 8, R_HEAD );
}
