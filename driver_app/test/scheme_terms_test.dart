import 'dart:convert';
import 'dart:io';

import 'package:fleet_driver/core/models.dart';
import 'package:fleet_driver/l10n/app_localizations.dart';
import 'package:fleet_driver/ui/screens/schemes.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// The server's own scheme templates, as the app receives a scheme made from them.
PayScheme fromTemplate(String code) {
  final all = jsonDecode(File('../backend/app/modules/payroll/rules/templates.json').readAsStringSync()) as List;
  final t = all.cast<Map<String, dynamic>>().firstWhere((x) => x['code'] == code);
  return PayScheme.fromJson({
    'id': code,
    'code': code,
    'name': t['name'],
    'calculator': 'blocks',
    'target_orders': 420,
    'required_valid_days': 0,
    'company_covers': <String>[],
    'steps': <Object>[],
    'blocks': t['blocks'],
  });
}

String strip(String s) => s.replaceAll(RegExp('[\\u2066\\u2069]'), '');

void main() {
  test(
    'a Keeta fixed-salary scheme reads in full: salary, target, bonuses, marks, star day, sheet, expenses',
    () async {
      final l = await AppLocalizations.delegate.load(const Locale('ar'));
      final lines = SchemeCard.blockTerms(l, fromTemplate('keeta_fixed_200').blocks!, 'ar').map(strip).toList();
      expect(lines, [
        'علامة حمراء في يوم النجمة: كل طلبات الشهر بـ 0.200 د.ك بدل الراتب والبونص، والخصومات تُخصم منه',
        'أكثر من 4 علامات حمراء: كل طلبات الشهر بـ 0.200 د.ك بدل الراتب والبونص',
        'راتب ثابت: 200.000 د.ك في الشهر',
        'التارجت 420 طلب: كل طلب فوقه + 0.476 د.ك',
        'وكل طلب ناقص عن التارجت − 0.476 د.ك',
        'بونص الشرائح (أعلى شريحة تصلها فقط):',
        '• 510 طلب: 50.000 د.ك',
        '• 610 طلب: 100.000 د.ك',
        'العلامات الحمراء في الشهر:',
        '• حتى 2 علامات: بدون خصم (أيام إجازتك)',
        '• 3 علامات: − 10.000 د.ك',
        '• 4 علامات: − 30.000 د.ك',
        'البقشيش يُضاف لراتبك، وتعويض تلف الطعام والتعديلات وخصم المنصة تُخصم منه',
        'على الشركة: ${l.expense_housing}، ${l.expense_sim}، ${l.expense_maintenance}، ${l.expense_gas}',
      ]);
    },
  );

  test('Talabat: the batch table 1 to 7, and a fixed price with who pays what', () async {
    final l = await AppLocalizations.delegate.load(const Locale('en'));
    final batch = SchemeCard.blockTerms(l, fromTemplate('talabat_batch_plan').blocks!, 'en').map(strip).toList();
    expect(batch.where((x) => x.startsWith('• Batch ')).length, 7);
    expect(batch, contains('• Batch 1: 0.700 KWD'));
    expect(batch, contains('• Batch 7: 0.400 KWD'));
    expect(batch.last, startsWith('On you: '));
    final fixed = SchemeCard.blockTerms(l, fromTemplate('talabat_fixed_350').blocks!, 'en').map(strip).toList();
    expect(fixed.first, 'Per order: 0.350 KWD');
    expect(fixed.last, 'The company pays: maintenance, housing, gas, SIM');
  });
}
