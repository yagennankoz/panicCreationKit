* adpcm.h  ADPCM の音を、サンプリングレートを選んで鳴らす（PCMP は 15.6kHz だけ）  panicCreationKit のライブラリ
*
* 使い方（くわしくは docs/LIBRARY.md）：
*	.include	sch.h
*	.include	adpcm.h		* sch.h の後に
*	...
*	PCMR	pcm,pcm_end-pcm,2	* 音を 7.8kHz で鳴らす（鳴っている音は止めてから）
*	...
*	PCMS			* 音を止める（sch.h の命令のまま）
*	DEND
*	EXIT
*	.include	adpcm.s		* ルーチンの本体（EXIT の後、素材より前に）
*
* RATE（サンプリングレート）：0＝3.9kHz、1＝5.2kHz、2＝7.8kHz、3＝10.4kHz、4＝15.6kHz（PCMP と同じ）。
* 音は左右両方から出す。長さは約 12MB まで（64KB ごとに分けて最大 192 個、PCMP と同じ）。

PCMR:	.macro	ADDR,LEN,RATE	* ADPCM の音（ADDR から LEN バイト）を RATE で鳴らす。鳴っている音は止めてから
	BSB2	ad_play,ADDR,(RATE)*$1000000+(LEN)
	.endm
