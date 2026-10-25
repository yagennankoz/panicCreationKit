* timelog.h  時刻の記録：2 か所の時刻（1/100 秒）をファイルに書く  panicCreationKitForWin のライブラリ
*
* 使い方（くわしくは docs/LIBRARY.md）：
*	.include	sch.h
*	.include	timelog.h	* sch.h の後に
*	...
*	TLOG0				* はじめの時刻を覚える
*	...（測りたい所）
*	TLOG1				* 終わりの時刻を覚えて、ファイルに書く
*	DEND
*	EXIT
*	.include	timelog.s	* ルーチンの本体（EXIT の後）
* tl_fn:	.dc.b	'time.txt',0	* 書くファイルの名前（自分で書く）
* tl_exp:	.dc.b	'200',13,10	* EXPECT= の後に書く文字（自分で書く。予想の値など）
* tl_exp_end:
*	.even
*
* ファイルの中身：T0=xxxxxxxx T1=xxxxxxxx EXPECT=200（16 進、IOCS _ONTIME の 1/100 秒）。差 T1-T0 が測った時間。

TLOG0:	.macro			* はじめの時刻
	BSUB	tl_t0
	.endm

TLOG1:	.macro			* 終わりの時刻（ファイルに書く）
	BSUB	tl_t1
	.endm
