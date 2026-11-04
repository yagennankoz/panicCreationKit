* adpcm.s  ADPCM の音をサンプリングレートを選んで鳴らすルーチンの本体（adpcm.h のマクロから BSB2 で呼ばれる）
*          panicCreationKit のライブラリ
*
* スケジュールの EXIT の後に .include する。panic.x の PCMP と同じく、64KB ごとに分けた表を作って
* IOCS _ADPCMAOT（$62。アレイチェーンで再生）を呼ぶ。違うのは D1 の上のバイト（サンプリングレート）だけ。
* 先に IOCS _ADPCMMOD（$67、D1＝0）で鳴っている音を止める（表を書き換える前に止めるため）。
* 止めるのは sch.h の PCMS（ESC で抜けたときは panic.x が止める）。
* 先頭の 'PTAP' は pansim（PC 上のシミュレータ）が見分けるための印。消さないこと。
* 使うレジスタは全部戻す（D0・D1 は BSB2 の引数）。

ad_play:				* D0.l＝音のデータの頭、D1.l＝レート（上の 8 ビット）×$1000000＋長さ（下の 24 ビット）
	bra.s	ad_p0
	.dc.b	'PTAP'
ad_p0:	movem.l	d0-d4/a0-a1,-(sp)
	movea.l	d0,a1			* データの頭
	move.l	d1,d2
	andi.l	#$00ffffff,d2		* 長さ
	rol.l	#8,d1			* レートを下のバイトへ
	andi.w	#$0007,d1
	lsl.w	#8,d1
	ori.w	#$0003,d1		* 左右両方から出す
	move.w	d1,d4			* _ADPCMAOT の D1（レート×256＋出力）
	moveq.l	#0,d1
	moveq.l	#$67,d0			* _ADPCMMOD：鳴っている音を止める
	trap	#15
	lea	ad_chain,a0
	moveq.l	#0,d3			* 表の数
ad_p1:	tst.l	d2
	beq	ad_p3
	cmpi.w	#192,d3
	bcc	ad_p3			* 表がいっぱい（約 12MB）。残りは鳴らさない
	move.l	#$ffff,d0
	cmp.l	d0,d2
	bcc	ad_p2
	move.l	d2,d0			* 最後の残り
ad_p2:	move.l	a1,(a0)+		* アドレス
	move.w	d0,(a0)+		* 長さ（65535 まで）
	adda.l	d0,a1
	sub.l	d0,d2
	addq.w	#1,d3
	bra	ad_p1
ad_p3:	tst.w	d3
	beq	ad_p9			* 長さ 0 なら鳴らさない
	move.w	d4,d1
	lea	ad_chain,a1
	moveq.l	#0,d2
	move.w	d3,d2			* 表の数
	moveq.l	#$62,d0			* _ADPCMAOT
	trap	#15
ad_p9:	movem.l	(sp)+,d0-d4/a0-a1
	rts

	.even
ad_chain:	.ds.w	3*192		* アレイチェーンの表（アドレス.l、長さ.w）× 192
