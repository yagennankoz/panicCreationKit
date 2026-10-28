* zmusic.h  Z-MUSIC ver2 の FM 音源の曲・効果音を鳴らす／止める  panicCreationKitForWin のライブラリ
*
* 使い方（くわしくは docs/LIBRARY.md）：
*	.include	sch.h
*	.include	zmusic.h	* sch.h の後に
*	...
*	ZMVS	sev		* 効果音の音色を登録する（効果音に音色の定義があるとき。最初に 1 回）
*	ZMPL	bgm		* 曲を頭から鳴らす（鳴っている曲は止めてから）
*	...
*	ZSEP	se1,8		* 効果音 se1 をトラック 8 から鳴らす
*	ZSES	se1,8		* 効果音 se1（トラック 8 から）を止める
*	ZMFO	20		* 曲をフェードアウトする（1～85。大きいほど速い）
*	ZMST			* 曲を止める
*	DEND
*	EXIT
*	.include	zmusic.s	* ルーチンの本体（EXIT の後、素材より前に）
*
* bgm・se1・sev は mml2zmd（または mkparts）で作った素材のラベル（bgm＝.zmd、se1＝.zse、sev＝.zmv）。
* Z-MUSIC ver2（ZMSC.X か ZMUSIC.X）が常駐していないときは、どの命令も何もしない。

ZMPL:	.macro	ZMD		* 曲（.zmd）を頭から鳴らす。鳴っている曲は止めてから
	BSB1	zm_play,ZMD
	.endm

ZMST:	.macro			* 曲を止める（全部のトラック）
	BSUB	zm_stop
	.endm

ZMFO:	.macro	SPEED		* 曲をフェードアウトする（SPEED＝1～85、大きいほど速い）
	BSB1	zm_fade,SPEED
	.endm

ZSEP:	.macro	ZSE,TRACK	* 効果音（.zse）をトラック TRACK から鳴らす（曲のそのトラックは効果音の間だけ休む）
	BSB2	zm_se,ZSE,TRACK
	.endm

ZSES:	.macro	ZSE,TRACK	* 効果音（.zse、トラック TRACK から鳴らしたもの）を止める
	BSB2	zm_sestop,ZSE,TRACK
	.endm

ZMVS:	.macro	ZMV		* 音色（.zmv）を登録する
	BSB1	zm_voice,ZMV
	.endm
