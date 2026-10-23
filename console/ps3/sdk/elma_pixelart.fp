!!FP2.0
OPTION NV_fragment_program2;
MOVR R3, fragment.texcoord[1];
MOVR R4, fragment.texcoord[2];
MOVR R5, fragment.texcoord[3];
MULR R0.xy, fragment.texcoord[0], R3;
MADR R0.xy, -R4, R5.x, R0;
FRCR R1.xy, R0;
ADDR R0.xy, R0, -R1;
ADDR R1.xy, R1, R4;
ADDR R1.xy, R1, -R5.y;
MULR_SAT R1.xy, R1, R4.zwzw;
MULR R2.xy, R1, R1;
MADR R1.xy, -R1, R5.z, R5.w;
MADR R0.xy, R2, R1, R0;
ADDR R0.xy, R0, R5.x;
MULR R0.xy, R0, R3.zwzw;
TEXR result.color, R0, texture[0], 2D;
END
