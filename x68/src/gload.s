* gload.s : 256x256 の生データを 512x512 65536色画面の (0,0) に表示する
*   使い方: gload <file>   ... 画面モードを 512x512 65536色にして表示
*           gload          ... 画面モードを元（768x512）に戻す
*   <file> は 256x256 ドット、1ドット 1ワード（GRB 5:5:5:1、ビッグエンディアン）
*   計 131072 バイト。tools/make_ref_images.py が作る。
*   出典：panicCreationKit のために作ったもの（MIT-0。https://github.com/yagennankoz/panicCreationKit）

_CRTMOD		.equ	$10
_G_CLR_ON	.equ	$90
_B_PRINT	.equ	$21
_EXIT		.equ	$ff00
_EXIT2		.equ	$ff4c
_PRINT		.equ	$ff09
_OPEN		.equ	$ff3d
_READ		.equ	$ff3f
_CLOSE		.equ	$ff3e
_SUPER		.equ	$ff20

SIZE		.equ	256*256*2

	.text
start:
	lea	1(a2),a0		* コマンドライン
@@:	move.b	(a0)+,d0
	beq	reset
	cmp.b	#' ',d0
	beq	@b
	cmp.b	#9,d0
	beq	@b
	subq.l	#1,a0
	movea.l	a0,a1			* ファイル名の先頭
@@:	move.b	(a0)+,d0
	beq	@f
	cmp.b	#' ',d0
	bhi	@b
	clr.b	-1(a0)			* 末尾を 0 にする
@@:
	* ファイルを読む
	clr.w	-(sp)
	move.l	a1,-(sp)
	.dc.w	_OPEN
	addq.l	#6,sp
	move.l	d0,d7
	bmi	err_open
	move.l	#SIZE,-(sp)
	pea	buf
	move.w	d7,-(sp)
	.dc.w	_READ
	lea	10(sp),sp
	cmp.l	#SIZE,d0
	bne	err_read
	move.w	d7,-(sp)
	.dc.w	_CLOSE
	addq.l	#2,sp

	* 画面モード 12 = 512x512 65536色
	moveq.l	#12,d1
	moveq.l	#_CRTMOD,d0
	trap	#15
	moveq.l	#_G_CLR_ON,d0
	trap	#15

	* スーパーバイザーモードで GRAM に書く
	clr.l	-(sp)
	.dc.w	_SUPER
	move.l	d0,(sp)
	lea	buf,a0
	lea	$c00000,a1
	move.w	#256-1,d1
line:	movea.l	a1,a2
	move.w	#256/2-1,d2
@@:	move.l	(a0)+,(a2)+
	dbra	d2,@b
	lea	1024(a1),a1		* 1ライン = 512ドット x 2バイト
	dbra	d1,line
	.dc.w	_SUPER
	addq.l	#4,sp
	.dc.w	_EXIT

reset:
	moveq.l	#16,d1			* 768x512 16色（通常の画面）
	moveq.l	#_CRTMOD,d0
	trap	#15
	.dc.w	_EXIT

err_open:
	pea	msg_open
	bra	err
err_read:
	pea	msg_read
err:	.dc.w	_PRINT
	addq.l	#4,sp
	move.w	#1,-(sp)
	.dc.w	_EXIT2

	.data
msg_open:	.dc.b	'gload: ファイルを開けません',13,10,0
msg_read:	.dc.b	'gload: サイズが 131072 バイトではありません',13,10,0

	.bss
	.even
buf:	.ds.b	SIZE

	.end	start
