from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from decimal import Decimal, InvalidOperation
from .models import Produit, Vente, Remise, Paiement, Reassort
from .forms import VenteForm
import csv
from django.db.models import Sum, Q
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncYear
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime
import xlsxwriter
from io import BytesIO

MODES_PAIEMENT = [
    ('especes', 'Espèces'),
    ('carte', 'Carte'),
    ('cheque', 'Chèque'),
    ('ticket', 'Ticket Restaurant'),
]

def accueil(request):
    return render(request, 'caisse/accueil.html')

def importer_produits(request):
    if request.method == 'POST':
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(decoded_file)
        for row in reader:
            try:
                prix = Decimal(row['prix'])
                stock = int(row['stock'])
                Produit.objects.create(nom=row['nom'], prix=prix, stock=stock)
            except (InvalidOperation, ValueError):
                messages.error(request, f"Ligne invalide ignorée: {row}")
                continue
        messages.success(request, "Produits importés avec succès")
        return redirect('accueil')
    return render(request, 'caisse/importer_produits.html')

def rapports(request):
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    export_excel = request.GET.get('export_excel') == '1'

    filters = Q()
    if date_debut:
        try:
            debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
            filters &= Q(date_paiement__date__gte=debut)
        except ValueError:
            pass
    if date_fin:
        try:
            fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
            filters &= Q(date_paiement__date__lte=fin)
        except ValueError:
            pass

    paiements = Paiement.objects.filter(filters)

    ca_jour = paiements.annotate(date=TruncDay('date_paiement')).values('date').annotate(total=Sum('montant_paye')).order_by('date')
    ca_semaine = paiements.annotate(semaine=TruncWeek('date_paiement')).values('semaine').annotate(total=Sum('montant_paye')).order_by('semaine')
    ca_mois = paiements.annotate(mois=TruncMonth('date_paiement')).values('mois').annotate(total=Sum('montant_paye')).order_by('mois')
    ca_an = paiements.annotate(an=TruncYear('date_paiement')).values('an').annotate(total=Sum('montant_paye')).order_by('an')

    details_jour = []
    for jour in ca_jour:
        date_j = jour['date']
        modes_details = Paiement.objects.filter(date_paiement__date=date_j).values('mode').annotate(montant=Sum('montant_paye'))
        detail_modes = {mode['mode']: mode['montant'] for mode in modes_details}
        detail_modes['total'] = jour['total']
        detail_modes['date'] = date_j
        details_jour.append(detail_modes)

    ventes_list = Vente.objects.filter(paiements__in=paiements).distinct().order_by('-date_vente')
    paiements_list = paiements.order_by('-date_paiement')
    today = timezone.now().date()
    daily_total = paiements.filter(date_paiement__date=today).aggregate(total=Sum('montant_paye'))['total'] or Decimal('0')

    if export_excel:
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'remove_timezone': True})
        worksheet = workbook.add_worksheet('Rapports')

        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        total_format = workbook.add_format({'bold': True, 'bg_color': '#90EE90'})
        money_format = workbook.add_format({'num_format': '#,##0.00 €', 'border': 1})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy', 'border': 1})

        row = 0
        worksheet.write(row, 0, 'Période', header_format)
        worksheet.write(row, 1, date_debut or 'Début', date_format)
        worksheet.write(row, 2, date_fin or 'Fin', date_format)
        row += 2

        worksheet.write(row, 0, 'CA par Jour', header_format)
        row += 1
        headers = ['Date', 'Espèces', 'Carte', 'Chèque', 'Ticket', 'Total']
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_format)
        row += 1
        for detail in details_jour:
            worksheet.write(row, 0, detail['date'], date_format)
            worksheet.write(row, 1, detail.get('especes', 0), money_format)
            worksheet.write(row, 2, detail.get('carte', 0), money_format)
            worksheet.write(row, 3, detail.get('cheque', 0), money_format)
            worksheet.write(row, 4, detail.get('ticket', 0), money_format)
            worksheet.write(row, 5, detail['total'], total_format)
            row += 1
        row += 2

        worksheet.write(row, 0, 'CA par Semaine', header_format)
        row += 1
        worksheet.write(row, 0, 'Semaine', header_format)
        worksheet.write(row, 1, 'Total', header_format)
        row += 1
        for item in ca_semaine:
            worksheet.write(row, 0, str(item['semaine']), date_format)
            worksheet.write(row, 1, item['total'], money_format)
            row += 1
        row += 2

        worksheet.write(row, 0, 'CA par Mois', header_format)
        row += 1
        worksheet.write(row, 0, 'Mois', header_format)
        worksheet.write(row, 1, 'Total', header_format)
        row += 1
        for item in ca_mois:
            worksheet.write(row, 0, str(item['mois']), date_format)
            worksheet.write(row, 1, item['total'], money_format)
            row += 1
        row += 2

        worksheet.write(row, 0, 'CA par Année', header_format)
        row += 1
        worksheet.write(row, 0, 'Année', header_format)
        worksheet.write(row, 1, 'Total', header_format)
        row += 1
        for item in ca_an:
            worksheet.write(row, 0, str(item['an']), date_format)
            worksheet.write(row, 1, item['total'], money_format)
            row += 1
        row += 2

        worksheet.write(row, 0, 'Ventes Détaillées', header_format)
        row += 1
        headers = ['Produit', 'Quantité', 'Total', 'Date']
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_format)
        row += 1
        for vente in ventes_list:
            worksheet.write(row, 0, vente.produit.nom)
            worksheet.write(row, 1, vente.quantite)
            worksheet.write(row, 2, vente.total, money_format)
            worksheet.write(row, 3, vente.date_vente, date_format)
            row += 1
        row += 2

        worksheet.write(row, 0, 'Paiements Détaillés', header_format)
        row += 1
        headers = ['Mode', 'Montant', 'Date']
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_format)
        row += 1
        for paiement in paiements_list:
            worksheet.write(row, 0, paiement.get_mode_display())
            worksheet.write(row, 1, paiement.montant_paye, money_format)
            worksheet.write(row, 2, paiement.date_paiement, date_format)
            row += 1

        workbook.close()
        output.seek(0)
        response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=rapports_caisse.xlsx'
        return response

    context = {
        'ca_jour': details_jour,
        'ca_semaine': ca_semaine,
        'ca_mois': ca_mois,
        'ca_an': ca_an,
        'ventes_list': ventes_list,
        'paiements_list': paiements_list,
        'daily_total': daily_total,
        'date_debut': date_debut,
        'date_fin': date_fin,
    }
    return render(request, 'caisse/rapports.html', context)

def produits_critiques(request):
    SEUIL_CRITIQUE = 5
    produits_critiques = Produit.objects.filter(stock__lte=SEUIL_CRITIQUE)
    context = {'produits_critiques': produits_critiques, 'seuil': SEUIL_CRITIQUE}
    return render(request, 'caisse/produits_critiques.html', context)

def reassort_produit(request, produit_id):
    produit = get_object_or_404(Produit, id=produit_id)
    if request.method == 'POST':
        try:
            quantite = int(request.POST['quantite'])
            if quantite > 0:
                produit.stock += quantite
                produit.save()
                Reassort.objects.create(produit=produit, quantite_ajoutee=quantite)
                messages.success(request, f"Réassort de {quantite} unités pour {produit.nom}")
            else:
                messages.error(request, "Quantité doit être positive")
        except ValueError:
            messages.error(request, "Quantité invalide")
        return redirect('caisse')
    return render(request, 'caisse/reassort_form.html', {'produit': produit})

def reassort_auto(request):
    SEUIL_MIN = 5
    STOCK_CIBLE = 20
    produits = Produit.objects.filter(stock__lte=SEUIL_MIN)
    reassortés = []
    for produit in produits:
        a_ajouter = STOCK_CIBLE - produit.stock
        if a_ajouter > 0:
            produit.stock += a_ajouter
            produit.save()
            Reassort.objects.create(produit=produit, quantite_ajoutee=a_ajouter)
            reassortés.append(produit)
    messages.success(request, f"Réassort auto effectué sur {len(reassortés)} produits")
    return redirect('produits_critiques')

def get_panier_dict(request):
    panier = request.session.get('panier', {})
    if not isinstance(panier, dict):
        panier = {}
    cleaned_panier = {str(key): int(value) for key, value in panier.items() if isinstance(value, (int, str)) and int(value) > 0}
    request.session['panier'] = cleaned_panier
    request.session.modified = True
    return cleaned_panier

def get_panier_ventes(panier_dict):
    ventes = []
    for str_id, quantite in panier_dict.items():
        try:
            produit_id = int(str_id)
            produit = Produit.objects.get(id=produit_id)
            subtotal = produit.prix * quantite
            ventes.append({'produit': produit, 'quantite': quantite, 'total': subtotal})
        except (ValueError, Produit.DoesNotExist):
            pass
    return ventes

def calculer_total_panier(request):
    panier = get_panier_dict(request)
    total = Decimal('0')
    for str_id, quantite in panier.items():
        try:
            produit_id = int(str_id)
            produit = Produit.objects.get(id=produit_id)
            subtotal = produit.prix * quantite
            remises_article = Remise.objects.filter(appliquee_a_produit=produit, appliquee_a_vente__isnull=True)
            for remise in remises_article:
                deduction = remise.appliquer(subtotal)
                subtotal = max(Decimal('0'), subtotal - deduction)
            total += subtotal
        except (ValueError, Produit.DoesNotExist):
            pass
    remises_globales = Remise.objects.filter(appliquee_a_produit__isnull=True, appliquee_a_vente__isnull=True)
    for remise in remises_globales:
        deduction = remise.appliquer(total)
        total = max(Decimal('0'), total - deduction)
    return total

@csrf_exempt
def caisse(request):
    produits = Produit.objects.all()
    panier = get_panier_dict(request)
    total = calculer_total_panier(request)
    panier_ventes = get_panier_ventes(panier)
    form = VenteForm()
    
    if request.method == 'POST':
        request.session.modified = True
        
        if 'produit' in request.POST:
            try:
                produit_id = int(request.POST['produit'])
                str_id = str(produit_id)
                produit = get_object_or_404(Produit, id=produit_id)
                if produit.stock >= 1:
                    panier[str_id] = panier.get(str_id, 0) + 1
                    request.session['panier'] = panier
                    produit.stock -= 1
                    produit.save()
                    new_total = calculer_total_panier(request)
                    new_panier_ventes = get_panier_ventes(panier)
                    new_panier_html = render_to_string('caisse/panier_list.html', {'panier_ventes': new_panier_ventes}, request=request)
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True, 'total': str(new_total), 'panier_html': new_panier_html})
                    messages.success(request, f"{produit.nom} ajouté au panier")
                else:
                    error = 'Stock insuffisant pour cet article'
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': error})
                    messages.error(request, error)
            except ValueError:
                messages.error(request, "ID produit invalide")
            return redirect('caisse')
                
        elif 'ajouter_nouveau' in request.POST:
            nom = request.POST.get('nom', '').strip()
            prix_str = request.POST.get('prix', '0')
            stock_str = request.POST.get('stock', '0')
            try:
                prix = Decimal(prix_str)
                stock = int(stock_str)
                if nom and prix > 0 and stock >= 0:
                    Produit.objects.create(nom=nom, prix=prix, stock=stock)
                    messages.success(request, f"Produit {nom} ajouté avec succès")
                else:
                    messages.error(request, "Données invalides pour le nouveau produit")
            except (ValueError, InvalidOperation):
                messages.error(request, "Prix ou stock invalide")
            return redirect('caisse')
                
        elif 'supprimer_produit' in request.POST:
            try:
                produit_id = int(request.POST['supprimer_produit'])
                produit = get_object_or_404(Produit, id=produit_id)
                produit.delete()
                messages.success(request, f"Produit {produit.nom} supprimé définitivement")
            except ValueError:
                messages.error(request, "ID produit invalide")
            return redirect('caisse')
                
        elif 'appliquer_remise' in request.POST:
            type_remise = request.POST.get('type_remise', 'pourcentage')
            valeur_str = request.POST.get('valeur_remise', '0')
            try:
                valeur = Decimal(valeur_str)
                if valeur > 0 and (type_remise == 'pourcentage' and valeur <= 100 or type_remise == 'fixe'):
                    Remise.objects.create(type=type_remise, valeur=valeur)
                    messages.success(request, "Remise globale appliquée avec succès")
                else:
                    messages.error(request, "Valeur de remise invalide")
            except InvalidOperation:
                messages.error(request, "Valeur remise invalide")
            return redirect('caisse')
                
        elif 'appliquer_remise_article' in request.POST:
            try:
                index = int(request.POST['appliquer_remise_article'])
                if 0 <= index < len(panier_ventes):
                    item = panier_ventes[index]
                    produit = item['produit']
                    type_remise = request.POST.get('type_remise', 'pourcentage')
                    valeur_str = request.POST.get('valeur_remise', '0')
                    valeur = Decimal(valeur_str)
                    if valeur > 0 and (type_remise == 'pourcentage' and valeur <= 100 or type_remise == 'fixe'):
                        Remise.objects.create(type=type_remise, valeur=valeur, appliquee_a_produit=produit)
                        messages.success(request, f"Remise appliquée sur {produit.nom}")
                    else:
                        messages.error(request, "Valeur de remise invalide")
                else:
                    messages.error(request, "Article invalide")
            except (ValueError, InvalidOperation):
                messages.error(request, "Données invalides pour la remise article")
            return redirect('caisse')
                
        elif 'remove_item' in request.POST:
            try:
                index = int(request.POST['remove_item'])
                if 0 <= index < len(panier_ventes):
                    item = panier_ventes[index]
                    produit_id = item['produit'].id
                    str_id = str(produit_id)
                    if str_id in panier:
                        panier[str_id] -= 1
                        produit = item['produit']
                        produit.stock += 1
                        produit.save()
                        if panier[str_id] <= 0:
                            del panier[str_id]
                        request.session['panier'] = panier
                        messages.success(request, "Article retiré du panier")
                else:
                    messages.error(request, "Article invalide")
            except ValueError:
                messages.error(request, "ID invalide")
            return redirect('caisse')
                
        elif 'vider_panier' in request.POST:
            for str_id, quantite in list(panier.items()):
                try:
                    produit_id = int(str_id)
                    produit = Produit.objects.get(id=produit_id)
                    produit.stock += quantite
                    produit.save()
                except (ValueError, Produit.DoesNotExist):
                    pass
            request.session['panier'] = {}
            messages.success(request, "Panier vidé et stocks restaurés")
            return redirect('caisse')
        
        elif 'payer' in request.POST:
            modes = []
            montants = []
            i = 0
            while f'mode_paiement_{i}' in request.POST:
                mode = request.POST.get(f'mode_paiement_{i}', '').strip()
                montant_str = request.POST.get(f'montant_{i}', '0')
                try:
                    montant = Decimal(montant_str)
                    if montant > 0 and mode:
                        modes.append(mode)
                        montants.append(montant)
                except InvalidOperation:
                    pass
                i += 1
            sum_montants = sum(montants)
            if abs(sum_montants - total) < Decimal('0.01') and panier and modes:
                ventes_crees = []
                for str_id, quantite in list(panier.items()):
                    try:
                        produit_id = int(str_id)
                        produit = Produit.objects.get(id=produit_id)
                        subtotal_brut = produit.prix * quantite
                        remises_article = Remise.objects.filter(appliquee_a_produit=produit, appliquee_a_vente__isnull=True)
                        subtotal = subtotal_brut
                        for remise in remises_article:
                            deduction = remise.appliquer(subtotal)
                            subtotal = max(Decimal('0'), subtotal - deduction)
                        vente = Vente.objects.create(produit=produit, quantite=quantite, total=subtotal)
                        ventes_crees.append(vente)
                        for remise in remises_article:
                            remise.appliquee_a_vente = vente
                            remise.save()
                    except (ValueError, Produit.DoesNotExist):
                        pass
                remises_globales = Remise.objects.filter(appliquee_a_produit__isnull=True, appliquee_a_vente__isnull=True)
                for remise in remises_globales:
                    if ventes_crees:
                        remise.appliquee_a_vente = ventes_crees[0]
                        remise.save()
                if ventes_crees:
                    for j, mode in enumerate(modes):
                        Paiement.objects.create(vente=ventes_crees[-1], mode=mode, montant_paye=montants[j])
                    messages.success(request, f"Paiement enregistré ! Total: {total} €")
                else:
                    messages.error(request, "Erreur lors de la création des ventes")
                request.session['panier'] = {}
                Remise.objects.filter(appliquee_a_vente__isnull=True).delete()
            else:
                messages.error(request, f"Montant payé {sum_montants} ≠ total {total} ou panier vide ou modes manquants")
            return redirect('caisse')
        
    context = {
        'produits': produits,
        'form': form,
        'panier_ventes': panier_ventes,
        'total': total,
        'modes_paiement': MODES_PAIEMENT,
    }
    return render(request, 'caisse/caisse.html', context)