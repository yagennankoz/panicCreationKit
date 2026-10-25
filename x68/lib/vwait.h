* vwait.h  VWAIT：再生の頭からの「予定の時刻」で待つ（TMWA の代わり）  panicCreationKitForWin のライブラリ
*
* 使い方（くわしくは docs/LIBRARY.md）：
*	.include	sch.h
*	.include	vwait.h		* sch.h の後に
*	...
*	TMWA	1			* タイマーの基準（V-Sync にそろえる）
*	VWINIT				* ここから予定の時刻を数える
*	VWADJ	555,-1			* （必要なら）予定の時刻が 555 カウント進むごとに 1 カウント早める
*	DRW0	...
*	VWAIT	4			* 予定の時刻を 4 カウント進めて、そこまで待つ
*	...
*	DEND
*	EXIT
*	.include	vwait.s		* ルーチンの本体（EXIT の後、素材より前に）
*
* 1 カウント＝V-Sync 1 回（約 18.03ms）。TMWA と同じ単位。

VWINIT:	.macro			* 予定の時刻を 0 にする（基準）
	BSUB	vw_init
	.endm

VWAIT:	.macro	COUNT		* 予定の時刻を COUNT 進めて、そこまで待つ
	BSB1	vw_wait,COUNT
	.endm

VWADJ:	.macro	EVERY,DELTA	* 予定の時刻が EVERY 進むごとに DELTA を足す（負＝早める、正＝遅らせる。EVERY＝0 でやめる）
	BSB2	vw_adj,EVERY,DELTA
	.endm
