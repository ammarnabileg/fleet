import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:uuid/uuid.dart';

import '../l10n/app_localizations.dart';

/// A photo kept in the app's own folder (it must survive until it is uploaded, possibly hours later).
class TakenPhoto {
  TakenPhoto(this.path, this.takenAt, {this.lat, this.lng});

  final String path;
  final DateTime takenAt;
  final double? lat;
  final double? lng;
}

/// Where photos come from. Odometer and vehicle photos: the app's own camera only (no gallery). Documents and the
/// delivery-app screenshot: the camera or a picked file. Replaced by fakes in widget tests.
class Photos {
  static Future<TakenPhoto?> Function(BuildContext context) camera = _camera;
  static Future<TakenPhoto?> Function() gallery = _gallery;

  static Future<String> keep(String source) async {
    final dir = Directory(p.join((await getApplicationSupportDirectory()).path, 'outbox'));
    await dir.create(recursive: true);
    final target = p.join(
      dir.path,
      '${const Uuid().v4()}${p.extension(source).isEmpty ? '.jpg' : p.extension(source)}',
    );
    await File(source).copy(target);
    return target;
  }

  static Future<TakenPhoto?> _camera(BuildContext context) =>
      Navigator.of(context)
          .push<TakenPhoto>(MaterialPageRoute(builder: (_) => const CameraScreen(), fullscreenDialog: true));

  static Future<TakenPhoto?> _gallery() async {
    final x = await ImagePicker().pickImage(source: ImageSource.gallery, imageQuality: 85, maxWidth: 2000);
    if (x == null) return null;
    return TakenPhoto(await keep(x.path), DateTime.now());
  }
}

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  CameraController? _controller;
  String? _error;
  bool _taking = false;

  @override
  void initState() {
    super.initState();
    _open();
  }

  Future<void> _open() async {
    try {
      final cams = await availableCameras();
      final back = cams.firstWhere((c) => c.lensDirection == CameraLensDirection.back, orElse: () => cams.first);
      final c = CameraController(
        back,
        ResolutionPreset.high,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await c.initialize();
      if (!mounted) {
        await c.dispose();
        return;
      }
      setState(() => _controller = c);
    } catch (e) {
      setState(() => _error = '$e');
    }
  }

  Future<void> _take() async {
    final c = _controller;
    if (c == null || _taking) return;
    setState(() => _taking = true);
    try {
      final shot = await c.takePicture();
      final takenAt = DateTime.now();
      Position? pos;
      try {
        pos = await Geolocator.getLastKnownPosition();
      } catch (_) {
        pos = null;
      }
      final path = await Photos.keep(shot.path);
      if (mounted) Navigator.of(context).pop(TakenPhoto(path, takenAt, lat: pos?.latitude, lng: pos?.longitude));
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _taking = false);
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = _controller;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(AppLocalizations.of(context).takePhoto),
      ),
      body: _error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(_error!, style: const TextStyle(color: Colors.white)),
              ),
            )
          : c == null
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                Expanded(child: Center(child: CameraPreview(c))),
                Padding(
                  padding: const EdgeInsets.all(24),
                  child: GestureDetector(
                    onTap: _take,
                    child: Container(
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 4),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(5),
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: _taking ? Colors.grey : Colors.white,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
