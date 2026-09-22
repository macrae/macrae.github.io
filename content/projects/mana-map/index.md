---
title: Mana Map
slug: mana-map
date: 2026-09-22
status: published
summary: "A workbench for designing and measuring Magic: the Gathering Commander decks, built on a 34,900-card embedding atlas and a seeded simulator."
category: machine-learning
tags: [latent-space]
---

Mana Map is a workbench for crafting, experimenting on, and analysing Commander
decks. It is built on one idea: **a claim about a deck is worth what the
experiment behind it is worth.**

Underneath it there is an embedding pipeline over roughly 34,900 Magic cards —
two small neural networks, a two-dimensional projection, and an interactive
atlas you can walk through by relation rather than by search. Two embedding
spaces do two different jobs: one lays the map out by colour and type, the other
answers what a card actually *does*, which is the only one similarity is ever
read from.

The centre of it is simulation. A headless, seeded game engine plays the deck
several hundred times against a fixed table of opponents; a seeded Monte Carlo
answers the questions that are about a curve rather than a table; and a
controlled A/B compares two versions of one list on one table. Every figure
carries its interval, its sample size, and the assumptions it was measured
under — or it does not get published.

Three things are worth saying plainly about it.

**Every number is arithmetic you can re-derive.** The pipeline and the analysis
commands make no calls to a language model at all. Where judgement enters, it is
labelled as judgement and kept apart from measurement.

**It is honest about what it cannot see.** The simulator's opponents are an AI,
the samples are small enough to matter, and a model that has never been taught
to read a card will report that card as having no effect — which looks identical
to a card that genuinely does nothing. Each of those is stated wherever a figure
that depends on it appears.

**It was built for one player.** It is open source so anyone can stand up their
own bench, not so that anyone else is supported.

<a class="sm-depart-card" href="/mana-map/">
<strong>Open the workbench &#8599;</strong>
<span>The card atlas, the deck pages, and the handbooks — all rendering
committed artifacts, no server required.</span>
</a>

The source is at [github.com/macrae/mana-map](https://github.com/macrae/mana-map).
