* timelog.s  時刻の記録のルーチン（timelog.h のマクロ、または BSUB tl_t0／tl_t1 で呼ぶ）  panicCreationKit のライブラリ
*
* スケジュールの EXIT の後に .include する。使う側で次のラベルを書くこと：
*   tl_fn       書くファイルの名前（0 で終わる）
*   tl_exp～tl_exp_end  「EXPECT=」の後に書く文字（改行 13,10 まで含める）
* 時刻は IOCS _ONTIME（起動からの 1/100 秒）。ファイルは DOS _CREATE で作り直す。レジスタは全部戻す。

_ONTIME	.equ	$7f
tl_t0:	movem.l	d0-d7/a0-a6,-(sp)
	moveq.l	#_ONTIME,d0
	trap	#15
	move.l	d0,tl_v0
	movem.l	(sp)+,d0-d7/a0-a6
	rts
tl_t1:	movem.l	d0-d7/a0-a6,-(sp)
	moveq.l	#_ONTIME,d0
	trap	#15
	move.l	d0,tl_v1
	move.l	tl_v0,d0
	lea	tl_h0,a0
	bsr	tl_hex
	move.l	tl_v1,d0
	lea	tl_h1,a0
	bsr	tl_hex
	move.w	#$20,-(sp)		* DOS _CREATE（属性：普通のファイル）
	pea	tl_fn
	.dc.w	$ff3c
	addq.l	#6,sp
	move.l	d0,d7
	bmi	@f
	pea	tl_end-tl_txt		* DOS _WRITE：T0=… T1=… EXPECT=
	pea	tl_txt
	move.w	d7,-(sp)
	.dc.w	$ff40
	lea	10(sp),sp
	pea	tl_exp_end-tl_exp	* DOS _WRITE：EXPECT= の後（使う側の tl_exp）
	pea	tl_exp
	move.w	d7,-(sp)
	.dc.w	$ff40
	lea	10(sp),sp
	move.w	d7,-(sp)		* DOS _CLOSE
	.dc.w	$ff3e
	addq.l	#2,sp
@@:	movem.l	(sp)+,d0-d7/a0-a6
	rts
tl_hex:	moveq.l	#8-1,d2			* d0 を 16 進 8 桁で (a0) へ
@@:	rol.l	#4,d0
	move.b	d0,d1
	and.w	#$0f,d1
	move.b	tl_dig(pc,d1.w),(a0)+
	dbra	d2,@b
	rts
tl_dig:	.dc.b	'0123456789ABCDEF'
	.even
tl_v0:	.dc.l	0
tl_v1:	.dc.l	0
tl_txt:	.dc.b	'T0='
tl_h0:	.dc.b	'00000000 T1='
tl_h1:	.dc.b	'00000000 EXPECT='
tl_end:
	.even
