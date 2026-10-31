import 'dart:typed_data';

import 'package:flutter/material.dart';

/// The office's splash screen: one image it designed (any layout, logo or text it wants), on its background color,
/// for a few seconds when the app opens.
class SplashView extends StatelessWidget {
  const SplashView({super.key, required this.image, required this.color});

  final Uint8List image;
  final String color; // #RRGGBB

  @override
  Widget build(BuildContext context) => Scaffold(
    key: const Key('splash'),
    backgroundColor: Color(int.parse(color.substring(1), radix: 16) | 0xFF000000),
    body: SizedBox.expand(
      child: Image.memory(
        image,
        fit: BoxFit.contain,
        gaplessPlayback: true,
        errorBuilder: (_, _, _) => const SizedBox(),
      ),
    ),
  );
}
