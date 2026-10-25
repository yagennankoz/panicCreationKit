* vwait.s  VWAIT のルーチンの本体（vwait.h のマクロから BSUB／BSB1／BSB2 で呼ばれる）  panicCreationKitForWin のライブラリ
*
* スケジュールの EXIT の後に .include する。panic.x V1.38.01 の作業領域（A6）を使う：
*   $2C8(A6).w  V-Sync のカウンタ（V-Sync の割り込みで +1。TMWA が 0 に戻して使う）
*   $2E0(A6).b  ESC の印（立っていれば panic.x は次の命令で終わる）
* TMWA は遅れたコマの分を取り戻さないが、VWAIT はカウンタを積み上げて「予定の時刻」まで待つので、
* 遅れても後のコマに余裕があれば取り戻す。すでに予定を過ぎていたら次の V-Sync まで待つだけ。
* VWADJ（vw_adj）：予定の時刻を進めた量を vw_acc に数え、vw_every に達するたびに予定の時刻へ vw_delta を足す
* （音とのわずかなずれを、一定時間ごとに 1 カウントずつ直す）。
* 先頭の 'PTVI'／'PTVW'／'PTVA' は pansim（PC 上のシミュレータ）が見分けるための印。消さないこと。
* 使うレジスタは全部戻す（D0・D1 は BSB1／BSB2 の引数）。

vw_init:
	bra.s	vw_i0
	.dc.b	'PTVI'
vw_i0:	move.l	d1,-(sp)
	move.w	$2c8(a6),d1		* panic.x の V-Sync のカウンタ（今までの分は捨てる）
	sub.w	d1,$2c8(a6)
	clr.l	vw_now
	clr.l	vw_target
	clr.l	vw_acc
	move.l	(sp)+,d1
	rts
vw_adj:					* D0.l＝何カウントごと（0 でやめる）、D1.l＝足すカウント（負なら早める）
	bra.s	vw_a0
	.dc.b	'PTVA'
vw_a0:	move.l	d0,vw_every
	move.l	d1,vw_delta
	clr.l	vw_acc
	rts
vw_wait:				* D0.l＝待つカウント（BSB1 の引数）
	bra.s	vw_w0
	.dc.b	'PTVW'
vw_w0:	movem.l	d0-d2,-(sp)
	add.l	d0,vw_target		* 予定の時刻を進める
	move.l	vw_every,d2		* 補正：進めた量が vw_every に達するたびに vw_delta を足す
	beq	vw_w4
	add.l	d0,vw_acc
vw_w5:	cmp.l	vw_acc,d2
	bhi	vw_w4
	sub.l	d2,vw_acc
	move.l	vw_delta,d1
	add.l	d1,vw_target
	bra	vw_w5
vw_w4:	bsr	vw_take
	move.l	vw_now,d2
	cmp.l	vw_target,d2
	blt	vw_w2
	addq.l	#1,d2			* もう過ぎている：次の V-Sync まで待つだけ
vw_w1:	tst.b	$2e0(a6)		* ESC が押された
	bne	vw_w3
	bsr	vw_take
	cmp.l	vw_now,d2
	bhi	vw_w1
	bra	vw_w3
vw_w2:	tst.b	$2e0(a6)
	bne	vw_w3
	bsr	vw_take
	move.l	vw_now,d0
	cmp.l	vw_target,d0
	blt	vw_w2
vw_w3:	movem.l	(sp)+,d0-d2
	rts
vw_take:				* カウンタを vw_now に移す（読みと引き算の間に割り込みが入らないよう sub で 1 命令）
	moveq.l	#0,d1
	move.w	$2c8(a6),d1
	sub.w	d1,$2c8(a6)
	add.l	d1,vw_now
	rts
	.even
vw_now:	.dc.l	0
vw_target:	.dc.l	0
vw_every:	.dc.l	0
vw_delta:	.dc.l	0
vw_acc:	.dc.l	0
