* zmusic.s  Z-MUSIC ver2 のルーチンの本体（zmusic.h のマクロから BSUB／BSB1／BSB2 で呼ばれる）  panicCreationKit のライブラリ
*
* スケジュールの EXIT の後に .include する。Z-MUSIC ver2 のファンクションコール（trap #3。マニュアル ZM10.MAN）を使う：
*   $0A m_stop（D2＝D3＝D4＝0 で全トラック）、$11 play_cnv_data（D2＝0：データを転送せず、その場所のまま鳴らす。
*   鳴っている曲は止めてから鳴らす）、
*   $12 se_play（効果音）、$1A fade_out、$04 m_vset／$1B m_vset2（音色の登録）。
* 曲のデータ（.zmd）は .pan の中に置いたまま鳴らすので、Z-MUSIC のトラックバッファは要らない（zmsc -t0 -w0 でよい）。
* 時間（10MHz、エミュレータで実測）：m_stop 約 25ms、play_cnv_data は zmsc -n（初期化なし）なら約 1ms・ふつうは約 118ms。
* 再生側は zmsc -n -t0 -w0 で常駐させるのがよい。
* 常駐の確認：trap #3 のベクタがメインメモリを指し、その 8 バイト前に 'ZmuSiC' と版（上位バイト $2x＝ver2）があるか（ZM10.MAN のリスト 1）。
*   無ければ何もしない（trap #3 が未定義のまま呼ぶと止まるため。ver3 は呼び方が違うので呼ばない）。
* 先頭の 'PTZ?' は pansim（PC 上のシミュレータ）が見分けるための印。消さないこと。
* 使うレジスタは全部戻す（D0・D1 は BSB1／BSB2 の引数）。

zm_play:				* D0.l＝曲のデータ（.zmd の頭。偶数番地）
	bra.s	zm_p0
	.dc.b	'PTZP'
zm_p0:	movem.l	d0-d2/a0-a1,-(sp)	* 鳴っている曲は play_cnv_data が止める（キーを離し、演奏するトラックの表を作り直す）。
	movea.l	d0,a1			* m_stop（約 25ms）は呼ばない
	bsr	zm_chk
	bne	zm_p9
	addq.l	#7,a1			* 版の番号の所（ZMD の頭＋7）を渡す
	moveq.l	#0,d2			* 0＝転送せず、その場所のまま鳴らす
	moveq.l	#$11,d1			* play_cnv_data
	trap	#3
zm_p9:	movem.l	(sp)+,d0-d2/a0-a1
	rts

zm_stop:				* 曲を止める
	bra.s	zm_s0
	.dc.b	'PTZS'
zm_s0:	movem.l	d0-d4/a0,-(sp)
	bsr	zm_chk
	bne	zm_s9
	moveq.l	#0,d2
	moveq.l	#0,d3
	moveq.l	#0,d4
	moveq.l	#$0a,d1			* m_stop（全トラック）
	trap	#3
zm_s9:	movem.l	(sp)+,d0-d4/a0
	rts

zm_fade:				* D0.l＝速さ（1～85）
	bra.s	zm_f0
	.dc.b	'PTZF'
zm_f0:	movem.l	d0-d2/a0,-(sp)
	move.l	d0,d2
	bsr	zm_chk
	bne	zm_f9
	moveq.l	#$1a,d1			* fade_out
	trap	#3
zm_f9:	movem.l	(sp)+,d0-d2/a0
	rts

zm_se:					* D0.l＝効果音のデータ（.zse の頭＝トラックの数。偶数番地）、D1.l＝トラック（1～32）
	bra.s	zm_e0
	.dc.b	'PTZE'
zm_e0:	movem.l	d0-d2/a0-a1,-(sp)
	movea.l	d0,a1
	move.l	d1,d2
	bsr	zm_chk
	bne	zm_e9
	moveq.l	#$12,d1			* se_play
	trap	#3
zm_e9:	movem.l	(sp)+,d0-d2/a0-a1
	rts

zm_sestop:				* D0.l＝効果音のデータ（.zse）、D1.l＝鳴らしたトラック
	bra.s	zm_x0			* 同じトラック・チャンネルに「すぐ終わる効果音」を割り込ませて止める
	.dc.b	'PTZX'			* （効果音が鳴り終わったときと同じく、曲のそのトラックは続きから鳴る）
zm_x0:	movem.l	d0-d3/a0-a2,-(sp)
	move.l	d1,d2
	movea.l	d0,a1
	bsr	zm_chk			* D0・A0 を壊すので先に
	bne	zm_x9
	movea.l	a1,a0
	lea	zm_xbuf,a1
	move.w	(a0)+,d0		* トラックの数（8 まで）
	cmpi.w	#8,d0
	bls	zm_x1
	moveq.l	#8,d0
zm_x1:	move.w	d0,(a1)+
	beq	zm_x9
	move.w	d0,d1
	mulu	#6,d1
	lea	(a1,d1.w),a2		* a2＝終わりの印（$FF）を置く所
	move.b	#$ff,(a2)
	subq.w	#1,d0
zm_x2:	move.l	a2,d3			* 終わりの印までの距離（この欄の 4 バイト後から数える）
	sub.l	a1,d3
	subq.l	#4,d3
	move.l	d3,(a1)+
	move.w	4(a0),(a1)+		* $00、チャンネル（元の効果音と同じ）
	addq.l	#6,a0
	dbra	d0,zm_x2
	lea	zm_xbuf,a1
	moveq.l	#$12,d1			* se_play
	trap	#3
zm_x9:	movem.l	(sp)+,d0-d3/a0-a2
	rts

zm_voice:				* D0.l＝音色の表（.zmv：.w 個数、1 つ 58 バイト＝ファンクション番号.b、音色番号.b、55 バイト、詰め物.b）
	bra.s	zm_v0
	.dc.b	'PTZV'
zm_v0:	movem.l	d0-d3/a0-a1,-(sp)
	movea.l	d0,a1
	bsr	zm_chk
	bne	zm_v9
	move.w	(a1)+,d3
	subq.w	#1,d3
	bmi	zm_v9
zm_v1:	moveq.l	#0,d1
	move.b	(a1)+,d1		* $04（m_vset）か $1B（m_vset2）
	moveq.l	#0,d2
	move.b	(a1)+,d2		* 音色番号（1～200）
	trap	#3			* a1＝55 バイトのデータ（trap #3 は d0・a0 のほかは壊さない）
	lea	56(a1),a1
	dbra	d3,zm_v1
zm_v9:	movem.l	(sp)+,d0-d3/a0-a1
	rts

zm_chk:					* Z-MUSIC ver2 が常駐しているか（Z＝1 なら常駐。D0・A0 を壊す）
	suba.l	a0,a0
	movea.l	$8c(a0),a0		* trap #3 のベクタ
	cmpa.l	#$00c00000,a0		* メインメモリ（12MB まで）の外なら常駐していない
	bcc	zm_c1			* （ROM・I/O などを読まない。読めない番地ならバスエラーになる）
	subq.l	#8,a0
	cmpi.l	#'ZmuS',(a0)+
	bne	zm_c1
	cmpi.w	#'iC',(a0)+
	bne	zm_c1
	move.b	(a0),d0			* 版の上位バイト（整数部と小数第 1 位。ver2 なら $2x）
	andi.b	#$f0,d0
	cmpi.b	#$20,d0
	rts
zm_c1:	moveq.l	#-1,d0
	rts

	.even
zm_xbuf:	.ds.b	2+6*8+2		* 効果音を止めるためのデータ（トラックの数、8 トラック分の欄、終わりの印）
	.even
